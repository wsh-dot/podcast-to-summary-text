from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _hostname(url):
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return ""


def _is_bilibili(hostname):
    return hostname == "bilibili.com" or hostname.endswith(".bilibili.com") or hostname == "b23.tv"


def _is_youtube(hostname):
    return (
        hostname in {"youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com"}
        or hostname.endswith(".youtube.com")
    )


def source_time_url(source_url, seconds):
    if not source_url:
        return None
    parts = urlsplit(source_url)
    host = _hostname(source_url)
    if not (_is_bilibili(host) or _is_youtube(host)):
        return source_url
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["t"] = str(max(0, int(seconds)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
