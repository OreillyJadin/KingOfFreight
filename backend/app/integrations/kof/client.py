from collections.abc import Iterator
from html import unescape
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from app.integrations.kof.catalog import ListDefinition
from app.integrations.kof.parser import (
    ParsedList,
    parse_phprunner_list,
    strip_more_suffix,
)

USER_AGENT = "FifthWheelSync/1.0 (authorized read-only data synchronization)"


class KofSiteError(RuntimeError):
    pass


class KofLoginError(KofSiteError):
    pass


class KofClient:
    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = "https://kingsoffreight.com/",
        *,
        capture_dir: str | Path | None = None,
        timeout: tuple[float, float] = (15, 180),
        max_retries: int = 3,
        backoff_seconds: float = 2,
    ) -> None:
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/") + "/"
        self.capture_dir = Path(capture_dir) if capture_dir else None
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            }
        )
        self._root_authenticated = False
        self._home_response: requests.Response | None = None
        self._authenticated_modules: set[str] = set()

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "KofClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        allowed_statuses: set[int] | None = None,
        **kwargs,
    ) -> requests.Response:
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(
                    method,
                    url,
                    timeout=self.timeout,
                    allow_redirects=False,
                    **kwargs,
                )
            except requests.RequestException as exc:
                if attempt + 1 == self.max_retries:
                    raise KofSiteError(
                        f"KOF {method.upper()} request failed after {self.max_retries} attempts"
                    ) from exc
                time.sleep(self.backoff_seconds * (2**attempt))
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt + 1 < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else None
                    except ValueError:
                        delay = None
                    time.sleep(delay or self.backoff_seconds * (2**attempt))
                    continue
            if method.upper() == "GET" and 300 <= response.status_code < 400:
                raise KofLoginError(
                    f"KOF GET {Path(urlparse(url).path).name} was redirected; "
                    "authentication failed or the session expired"
                )
            if response.status_code >= 400 and (
                allowed_statuses is None or response.status_code not in allowed_statuses
            ):
                raise KofSiteError(
                    f"KOF returned HTTP {response.status_code} for a read-only request"
                )
            return response
        raise KofSiteError(f"KOF {method.upper()} request failed")

    def _login_post(self, url: str, data: dict[str, str]) -> requests.Response:
        return self._request("POST", url, data=data)

    def login(self) -> None:
        if self._root_authenticated:
            return
        login_url = urljoin(self.base_url, "Lindex.php")
        login_page = self._request("GET", login_url)
        soup = BeautifulSoup(login_page.content, "lxml")
        form = soup.find("form")
        if form is None:
            raise KofLoginError("KOF login form was not found")
        action = form.get("action") or "Lindex.php"
        post_url = urljoin(login_page.url, action)
        parsed_action = urlparse(post_url)
        if (
            parsed_action.netloc != urlparse(self.base_url).netloc
            or Path(parsed_action.path).name.lower() != "lindex.php"
        ):
            raise KofLoginError("KOF login form targeted an unexpected endpoint")
        data = {
            item.get("name"): item.get("value", "")
            for item in form.find_all("input")
            if item.get("name")
        }
        data["txt_uname_email"] = self.username
        data["txt_password"] = self.password
        response = self._login_post(post_url, data)
        if response.status_code in {401, 403}:
            raise KofLoginError("KOF credentials were rejected")
        home = self._request("GET", urljoin(self.base_url, "emphome.php"))
        if self._looks_like_login(home.content):
            raise KofLoginError("KOF credentials were rejected")
        self._root_authenticated = True
        self._home_response = home

    def _looks_like_login(self, content: bytes) -> bool:
        soup = BeautifulSoup(content, "lxml")
        return bool(
            soup.find("input", attrs={"name": "txt_uname_email"})
            and soup.find("input", attrs={"name": "txt_password"})
        )

    def login_module(self, module: str) -> None:
        if module in self._authenticated_modules:
            return
        if module not in {"my_dispatch", "sales"}:
            raise KofSiteError("Requested KOF module is not allowed")
        self.login()
        home = self._home_response
        self._home_response = None
        if home is None:
            home = self._request("GET", urljoin(self.base_url, "emphome.php"))
        soup = BeautifulSoup(home.content, "lxml")
        prefix = f"{module}/"
        form = next(
            (
                item
                for item in soup.find_all("form")
                if (item.get("action") or "").lstrip("./").startswith(prefix)
            ),
            None,
        )
        if form is None:
            raise KofLoginError(f"KOF module login form was not found for {module}")
        data = {
            item.get("name"): item.get("value", "")
            for item in form.find_all("input")
            if item.get("name") and (item.get("type") or "hidden").lower() == "hidden"
        }
        module_login_url = urljoin(self.base_url, f"{module}/login.php")
        self._login_post(module_login_url, data)
        self._authenticated_modules.add(module)

    def _list_url(self, definition: ListDefinition) -> str:
        if definition.module not in {"my_dispatch", "sales"}:
            raise KofSiteError("Requested KOF module is not allowed")
        if not definition.filename.endswith("_list.php") or "/" in definition.filename:
            raise KofSiteError("Only KOF list pages may be requested")
        return urljoin(self.base_url, f"{definition.module}/{definition.filename}")

    def _capture(self, key: str, page: int, content: bytes) -> None:
        if self.capture_dir is None:
            return
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        safe_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", key)
        path = self.capture_dir / f"{safe_key}-page-{page:04d}.html"
        path.write_bytes(content)

    def get_list_page(
        self,
        definition: ListDefinition,
        page: int = 1,
        *,
        page_size: int = 500,
        extra_params: dict[str, str] | None = None,
    ) -> tuple[str, ParsedList]:
        self.login_module(definition.module)
        params = {"pagesize": str(page_size)}
        if page > 1:
            params["goto"] = str(page)
        if extra_params:
            params.update(extra_params)
        response = self._request("GET", self._list_url(definition), params=params)
        if self._looks_like_login(response.content):
            raise KofLoginError(
                f"KOF list access failed for {definition.key}; the module session expired"
            )
        self._capture(definition.key, page, response.content)
        parsed = parse_phprunner_list(response.content)
        if not parsed.columns and not BeautifulSoup(
            response.content, "lxml"
        ).select_one("table.rnr-gridtable"):
            raise KofSiteError(f"KOF returned a non-list page for {definition.key}")
        return response.text, parsed

    def get_fulltext(self, order_no: int, field: str) -> str | None:
        if order_no <= 0 or field not in {"Notes", "log"}:
            raise KofSiteError("Requested KOF full-text field is not allowed")
        self.login_module("my_dispatch")
        response = self._request(
            "GET",
            urljoin(self.base_url, "my_dispatch/fulltext.php"),
            params={
                "pagetype": "list",
                "table": "Master_Record_Sheet",
                "field": field,
                "key1": str(order_no),
            },
        )
        if self._looks_like_login(response.content):
            raise KofLoginError(
                "KOF full-text access failed; the module session expired"
            )
        try:
            payload = response.json()
        except ValueError:
            soup = BeautifulSoup(response.content, "lxml")
            paragraphs = soup.find_all("p")
            if len(paragraphs) != 1:
                return None
            try:
                payload = json.loads(paragraphs[0].decode_contents())
            except ValueError:
                return None
        if not isinstance(payload, dict) or payload.get("success") is not True:
            return None
        text = payload.get("textCont")
        if not isinstance(text, str):
            return None
        for _ in range(3):
            decoded_text = unescape(text)
            if decoded_text == text:
                break
            text = decoded_text
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        lines = []
        for line in text.replace("\t", "").splitlines():
            line = line.rstrip()
            if not line or re.fullmatch(r"-{5,}", line.strip()):
                continue
            lines.append(line)
        return strip_more_suffix("\n".join(lines)) or ""

    def iter_list_pages(
        self,
        definition: ListDefinition,
        *,
        page_size: int = 500,
        max_pages: int = 100,
        first_page_params: dict[str, str] | None = None,
    ) -> Iterator[tuple[int, str, ParsedList]]:
        for page in range(1, max_pages + 1):
            html, parsed = self.get_list_page(
                definition,
                page,
                page_size=page_size,
                extra_params=first_page_params,
            )
            yield page, html, parsed
            if len(parsed.rows) < page_size:
                return
        raise KofSiteError("KOF list exceeded the configured pagination safety limit")

    @staticmethod
    def order_number_sort_params(html: str | bytes) -> dict[str, str]:
        soup = BeautifulSoup(html, "lxml")
        header = soup.select_one("tr.rnr-toprow")
        if header is None:
            return {"orderby": "aOrder__", "order": "DESC"}
        for cell in header.find_all(["th", "td"], recursive=False):
            label = " ".join(cell.get_text(" ", strip=True).split()).lower()
            if label not in {"order #", "order number", "order no.", "order no"}:
                continue
            link = cell.get("data-href") or cell.get("href")
            if not link:
                child = cell.find(attrs={"data-href": True})
                link = child.get("data-href") if child else None
            if not link:
                continue
            query = parse_qs(urlparse(link).query)
            params = {
                key: value[0]
                for key, value in query.items()
                if value and key.lower() in {"orderby", "order", "ordtype"}
            }
            if params.get("orderby"):
                return params
        return {"orderby": "aOrder__", "order": "DESC"}


def load_captured_pages(capture_dir: str | Path, list_key: str) -> list[bytes]:
    safe_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", list_key)
    paths = sorted(Path(capture_dir).glob(f"{safe_key}-page-*.html"))
    return [path.read_bytes() for path in paths]


class CapturedKofClient:
    def __init__(
        self,
        capture_dir: str | Path,
        *,
        fulltext_client: KofClient | None = None,
    ) -> None:
        self.capture_dir = Path(capture_dir)
        self.fulltext_client = fulltext_client

    def __enter__(self) -> "CapturedKofClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def login_module(self, _: str) -> None:
        return None

    def get_fulltext(self, order_no: int, field: str) -> str | None:
        if self.fulltext_client is None:
            return None
        return self.fulltext_client.get_fulltext(order_no, field)

    def get_list_page(
        self,
        definition: ListDefinition,
        page: int = 1,
        *,
        page_size: int = 500,
        extra_params: dict[str, str] | None = None,
    ) -> tuple[str, ParsedList]:
        safe_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", definition.key)
        path = self.capture_dir / f"{safe_key}-page-{page:04d}.html"
        if not path.is_file():
            raise KofSiteError(f"Cached KOF page is missing for {definition.key}")
        content = path.read_bytes()
        return content.decode(errors="replace"), parse_phprunner_list(content)

    def iter_list_pages(
        self,
        definition: ListDefinition,
        *,
        page_size: int = 500,
        max_pages: int = 100,
        first_page_params: dict[str, str] | None = None,
    ) -> Iterator[tuple[int, str, ParsedList]]:
        safe_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", definition.key)
        previous_count = 0
        for page in range(1, max_pages + 1):
            path = self.capture_dir / f"{safe_key}-page-{page:04d}.html"
            if not path.is_file():
                if page == 1 or previous_count >= page_size:
                    raise KofSiteError(
                        f"Cached KOF page is missing for {definition.key}"
                    )
                return
            content = path.read_bytes()
            html = content.decode(errors="replace")
            parsed = parse_phprunner_list(content)
            yield page, html, parsed
            previous_count = len(parsed.rows)
            if len(parsed.rows) < page_size:
                return
        raise KofSiteError("Cached KOF list exceeded the pagination safety limit")

    @staticmethod
    def order_number_sort_params(html: str | bytes) -> dict[str, str]:
        return KofClient.order_number_sort_params(html)
