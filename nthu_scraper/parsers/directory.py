"""Pure directory parsing, retaining unknown field names and legacy cell values."""

from nthu_scraper.parsers import ParseError

URL_PREFIX = "https://tel.net.nthu.edu.tw/nthusearch/"
DEPARTMENT_TRANSLATION = {
    "分機": "extension",
    "直撥電話": "phone",
    "傳真電話": "fax",
    "Email": "email",
    "網頁": "website",
    "姓名": "name",
    "職稱/職責": "title",
    "備註": "note",
}


def translate_key(key: str) -> str:
    key = key.strip().replace("　", "")
    return DEPARTMENT_TRANSLATION.get(key, key)


def parse_department_link(link) -> dict[str, str]:
    href = (link.css("::attr(href)").get() or "").strip()
    name = (link.css("::text").get() or "").strip()
    if not href or not name:
        raise ParseError("Department listing contains an unusable link or name")
    return {"name": name, "url": URL_PREFIX + href}


def parse_contact_table(table) -> dict:
    contact = {}
    for row in table.css("tr"):
        cols = row.css("td")
        if len(cols) >= 2:
            key = (cols[0].css("::text").get() or "").strip()
            if not key:
                continue
            link = cols[1].css("a::attr(href)").get()
            text = cols[1].css("::text").get()
            if link:
                value = link.replace("mailto:", "") if "mailto:" in link else link
            else:
                value = text.strip() if text else "N/A"
            contact[translate_key(key)] = value
        elif cols:
            raise ParseError("Directory contact row has fewer than two cells")
    return contact


def parse_people_table(table) -> list[dict]:
    rows = table.css("tr")
    if not rows:
        return []
    header_texts = [cell.css("::text").get() for cell in rows[0].css("td")]
    headers = [
        text.strip() if text else f"header_{i}" for i, text in enumerate(header_texts)
    ]
    if not headers:
        raise ParseError("Directory people table has no column headers")
    people = []
    for row in rows[1:]:
        cols = row.css("td")
        if not cols:
            raise ParseError("Directory people row has no cells")
        person = {}
        for i, col in enumerate(cols):
            if i < len(headers):
                link = col.css("a::attr(href)").get()
                text = col.css("::text").get()
                person[translate_key(headers[i])] = (
                    link.replace("mailto:", "")
                    if link
                    else text.strip()
                    if text
                    else None
                )
        people.append(person)
    return people


def parse_department_details(page, departments: list[dict]) -> dict:
    """Combine already parsed child links with the optional contact/people tables."""
    if not page.css("div.story_left, div.story_max"):
        raise ParseError("Directory department page has no details containers")
    tables = page.css("div.story_max table")
    contact = parse_contact_table(tables[0]) if tables else {}
    people = parse_people_table(tables[1]) if len(tables) > 1 else []
    return {"departments": list(departments), "contact": contact, "people": people}


def parse_department_index(url: str) -> str | None:
    query = url.split("?")[1] if "?" in url else ""
    for param in query.split("&"):
        if "dd=" in param:
            return param.split("=")[1]
    return None
