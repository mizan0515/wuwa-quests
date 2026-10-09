"""Read-only checks for published HTML metadata, canonical sitemaps and footer.

These checks validate the local publication contract, not Google's indexing.
Google guidance: https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
"""
import argparse
import json
import re
from collections import Counter
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree

PUBLIC = 'https://mizan0515.github.io/wuwa-quests/'
STORY = 'https://ttaem.com/storytimeline/'
STORY_LABEL = '스토리 쉽게 보기'
SITE_TITLE = '명조 이야기 자료집'
GOOGLE_VERIFICATION = 'google450473d70e90c4cc.html'
GOOGLE_PROOF = ('google-site-verification: ' + GOOGLE_VERIFICATION).encode('utf-8')
XML_NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
PRIVATE_PATH = re.compile(r'(?i)(?<![a-z])[a-z]:[\\/]|file://|https?://(?:localhost|127\.0\.0\.1)(?=[:/]|$)')


def page_url(relative):
    return PUBLIC + quote(relative, safe='/')


def valid_google_proof(relative, content):
    return relative == GOOGLE_VERIFICATION and content == GOOGLE_PROOF


class Head(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.heads = 0
        self.inside = False
        self.title = None
        self.titles = []
        self.meta = []
        self.canonicals = []
        self.sitemaps = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.lang = attrs.get('lang')
        if tag == 'head':
            self.heads += 1
            self.inside = True
        if not self.inside:
            return
        if tag == 'title':
            self.title = []
            self.titles.append(self.title)
        elif tag == 'meta':
            self.meta.append(attrs)
        elif tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs.get('href', ''))
        elif tag == 'link' and attrs.get('rel') == 'sitemap':
            self.sitemaps.append(attrs.get('href', ''))

    def handle_endtag(self, tag):
        if tag == 'title':
            self.title = None
        if tag == 'head':
            self.inside = False

    def handle_data(self, data):
        if self.title is not None:
            self.title.append(data)

    def values(self, key, value):
        return [item.get('content', '') for item in self.meta if item.get(key) == value]


class Footer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.count = 0
        self.inside = False
        self.link = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'footer' and 'quest-footer' in attrs.get('class', '').split():
            self.count += 1
            self.inside = True
        if self.inside and tag == 'a':
            self.link = {'href': attrs.get('href'), 'text': []}
            self.links.append(self.link)

    def handle_endtag(self, tag):
        if tag == 'a':
            self.link = None
        if tag == 'footer':
            self.inside = False

    def handle_data(self, data):
        if self.link is not None:
            self.link['text'].append(data)


def parse_page(text):
    head = Head()
    # Parse only the head and footer fragments, keeping large transcripts out of
    # this metadata check. Other gates compare every original transcript row.
    head.feed(text.partition('</head>')[0] + '</head>')
    footer = Footer()
    for fragment in re.findall(r'<footer\b[^>]*>.*?</footer>', text, re.S):
        footer.feed(fragment)
    return head, footer


def metadata_errors(head, footer, relative):
    errors = []
    expected = page_url(relative)
    if head.heads != 1 or head.lang != 'ko':
        errors.append('head count or Korean language differs')
    titles = [''.join(value) for value in head.titles]
    if len(titles) != 1 or not titles[0].strip():
        errors.append('page must have one nonempty title')
    if head.canonicals != [expected]:
        errors.append('canonical differs from published HTML URL')
    descriptions = head.values('name', 'description')
    if len(descriptions) != 1 or not descriptions[0].strip():
        errors.append('page must have one nonempty description')
    if head.values('property', 'og:url') != [expected]:
        errors.append('Open Graph URL differs from canonical')
    if head.values('property', 'og:description') != descriptions:
        errors.append('Open Graph description differs from description')
    og_titles = head.values('property', 'og:title')
    if len(og_titles) != 1 or titles != [og_titles[0] + ' | ' + SITE_TITLE]:
        errors.append('page title and Open Graph title differ')
    if head.sitemaps != ['/wuwa-quests/sitemap-index.xml']:
        errors.append('page sitemap discovery link differs')
    if relative != '404.html' and blocked_directives(head):
        errors.append('reader robots or Googlebot metadata blocks indexing or following links')
    if relative == '404.html' and head.values('name', 'robots') != ['noindex, follow']:
        errors.append('404 must have one noindex follow robots directive')
    values = titles + head.canonicals + [item.get('content', '') for item in head.meta]
    if any(PRIVATE_PATH.search(value) for value in values):
        errors.append('local or private path exposed in metadata')
    links = [link for link in footer.links if link['href'] == STORY]
    if footer.count != 1 or len(links) != 1 or ''.join(links[0]['text']).strip() != STORY_LABEL:
        errors.append('shared footer story link missing, duplicated or mislabeled')
    return errors


def blocked_directives(head):
    return [item for item in head.meta
            if item.get('name', '').lower() in {'robots', 'googlebot'}
            and {'noindex', 'nofollow', 'none'} & set(re.split(r'[\s,]+', item.get('content', '').lower()))]


def sitemap_errors(urls, pages):
    errors = []
    counts = Counter(urls)
    if any(count != 1 for count in counts.values()):
        errors.append('sitemap contains duplicate URLs')
    for url in urls:
        if not isinstance(url, str):
            errors.append('sitemap URL is missing')
            continue
        if url == page_url(GOOGLE_VERIFICATION):
            errors.append('Google verification file included in sitemap')
            continue
        parsed = urlsplit(url)
        if parsed.query or parsed.fragment or url not in pages:
            errors.append('sitemap URL lacks a matching canonical HTML page: ' + url)
        elif pages[url]['relative'] == '404.html' or pages[url]['noindex']:
            errors.append('sitemap contains an error or noindex page: ' + url)
    expected = {url for url, page in pages.items()
                if page['relative'] != '404.html' and not page['noindex']}
    for url in sorted(expected - set(urls)):
        errors.append('indexable canonical page missing from sitemap: ' + url)
    return errors


def read_sitemaps(dist):
    errors, urls = [], []
    root = ElementTree.parse(dist / 'sitemap-index.xml').getroot()
    if root.tag != XML_NS + 'sitemapindex':
        return [], ['sitemap index XML root differs'], 0
    locations = [entry.findtext(XML_NS + 'loc') for entry in root.findall(XML_NS + 'sitemap')]
    if not locations or len(locations) != len(set(locations)):
        errors.append('sitemap index must contain distinct sitemap files')
    for location in locations:
        if not isinstance(location, str) or not location.startswith(PUBLIC):
            errors.append('sitemap file URL outside publication base')
            continue
        parsed = urlsplit(location)
        relative = unquote(parsed.path.removeprefix('/wuwa-quests/'))
        path = (dist / relative).resolve()
        if (parsed.query or parsed.fragment or not path.is_relative_to(dist.resolve())
                or not path.is_file() or not relative.endswith('.xml')
                or location != page_url(relative)):
            errors.append('sitemap index file is missing or has a noncanonical URL')
            continue
        document = ElementTree.parse(path).getroot()
        if document.tag != XML_NS + 'urlset':
            errors.append('sitemap URL set XML root differs')
            continue
        urls.extend(entry.findtext(XML_NS + 'loc') for entry in document.findall(XML_NS + 'url'))
    return urls, errors, len(locations)


def display(value):
    value = re.sub(r'^기타임무_유형(\d+)$', r'기타임무 (유형 \1)', value)
    return value.replace('버전미확인', '버전 미확인').replace('버전혼합_', '버전 혼합 ')


def verify(dist, site):
    errors, pages = [], {}
    manifest = json.loads((site / 'content-manifest.json').read_text(encoding='utf-8'))
    quests = {item['id']: item for item in manifest}
    descriptions, titles = Counter(), Counter()
    stats = {'htmlPages': 0, 'questDescriptions': 0, 'storyFooterLinks': 0,
             'googleVerificationFiles': 0, 'blockedReaderMetadata': 0}
    for path in sorted(dist.rglob('*.html')):
        relative = path.relative_to(dist).as_posix()
        if relative == GOOGLE_VERIFICATION:
            if not valid_google_proof(relative, path.read_bytes()):
                errors.append({'page': relative, 'error': 'Google public verification proof bytes differ'})
            stats['googleVerificationFiles'] += 1
            continue
        head, footer = parse_page(path.read_text(encoding='utf-8'))
        errors.extend({'page': relative, 'error': error} for error in metadata_errors(head, footer, relative))
        canonical = page_url(relative)
        noindex = any('noindex' in value.lower() for value in head.values('name', 'robots'))
        pages[canonical] = {'relative': relative, 'noindex': noindex}
        stats['htmlPages'] += 1
        stats['storyFooterLinks'] += sum(link['href'] == STORY for link in footer.links)
        stats['blockedReaderMetadata'] += int(relative != '404.html' and bool(blocked_directives(head)))
        descriptions.update(head.values('name', 'description'))
        titles.update(''.join(value) for value in head.titles)
        match = re.fullmatch(r'quests/(\d+)\.html', relative)
        if match:
            quest = quests.get(match[1])
            if quest is None:
                errors.append({'page': relative, 'error': 'quest metadata has no preserved manifest entry'})
                continue
            original = (site / 'originals' / (quest['id'] + '.txt')).read_text(encoding='utf-8-sig')
            scenes = len(re.findall(r'^장면 \d+: [^\n]+', original, re.M))
            expected = (display(quest['version']) + ' ' + display(quest['type']) + ' · ' + quest['title']
                        + ' · 퀘스트 ' + quest['id'] + ' · ' + str(scenes) + '개 장면의 한국어 대사와 선택지')
            if head.values('name', 'description') != [expected]:
                errors.append({'page': relative, 'error': 'quest description differs from ID and original scene scope'})
            if [''.join(value) for value in head.titles] != [quest['title'] + ' | ' + SITE_TITLE]:
                errors.append({'page': relative, 'error': 'original quest title changed'})
            stats['questDescriptions'] += 1
    if not pages:
        errors.append({'error': 'no published HTML pages'})
    if stats['questDescriptions'] != len(quests):
        errors.append({'error': 'whole preserved quest metadata coverage differs'})
    if stats['googleVerificationFiles'] != 1:
        errors.append({'error': 'Google public verification file missing from publication'})
    urls, xml_errors, sitemap_files = read_sitemaps(dist)
    errors.extend({'error': error} for error in xml_errors + sitemap_errors(urls, pages))
    stats.update(sitemapURLs=len(urls), sitemapFiles=sitemap_files,
                 duplicateTitleGroups=sum(count > 1 for count in titles.values()),
                 duplicateDescriptionGroups=sum(count > 1 for count in descriptions.values()))
    return {'status': 'FAIL' if errors else 'PASS', 'statistics': stats,
            'errorCount': len(errors), 'errors': errors[:30]}


def self_tests():
    url = page_url('people/scar.html')
    html = ('<!doctype html><html lang="ko"><head><title>스카 | ' + SITE_TITLE + '</title>'
            '<link rel="canonical" href="' + url + '"><link rel="sitemap" href="/wuwa-quests/sitemap-index.xml">'
            '<meta name="description" content="스카의 원문 자료"><meta property="og:title" content="스카">'
            '<meta property="og:url" content="' + url + '"><meta property="og:description" content="스카의 원문 자료">'
            '</head><body><footer class="quest-footer"><a href="' + STORY + '">' + STORY_LABEL + '</a></footer></body></html>')
    pages = {url: {'relative': 'people/scar.html', 'noindex': False}}
    error_html = html.replace(url, page_url('404.html')).replace('스카', '404')
    checks = [
        ('valid_metadata_and_footer', not metadata_errors(*parse_page(html), 'people/scar.html')),
        ('extensionless_canonical_rejected', bool(metadata_errors(*parse_page(html.replace(url, url[:-5], 1)), 'people/scar.html'))),
        ('duplicate_canonical_rejected', bool(metadata_errors(*parse_page(html.replace('</head>', '<link rel="canonical" href="' + url + '"></head>')), 'people/scar.html'))),
        ('missing_description_rejected', bool(metadata_errors(*parse_page(html.replace('<meta name="description" content="스카의 원문 자료">', '')), 'people/scar.html'))),
        ('wrong_og_url_rejected', bool(metadata_errors(*parse_page(html.replace('property="og:url" content="' + url, 'property="og:url" content="' + url + '?from=list')), 'people/scar.html'))),
        ('local_metadata_rejected', bool(metadata_errors(*parse_page(html.replace('스카의 원문 자료', escape('D:/game/private/source'))), 'people/scar.html'))),
        ('missing_footer_link_rejected', bool(metadata_errors(*parse_page(html.replace(STORY, 'https://ttaem.com/')), 'people/scar.html'))),
        ('wrong_footer_label_rejected', bool(metadata_errors(*parse_page(html.replace(STORY_LABEL, '다른 링크')), 'people/scar.html'))),
        ('robots_noindex_rejected', bool(metadata_errors(*parse_page(html.replace('</head>', '<meta name="robots" content="noindex"></head>')), 'people/scar.html'))),
        ('googlebot_nofollow_rejected', bool(metadata_errors(*parse_page(html.replace('</head>', '<meta name="googlebot" content="nofollow"></head>')), 'people/scar.html'))),
        ('robots_none_rejected', bool(metadata_errors(*parse_page(html.replace('</head>', '<meta name="robots" content="none"></head>')), 'people/scar.html'))),
        ('404_noindex_follow_accepted', not metadata_errors(*parse_page(error_html.replace('</head>', '<meta name="robots" content="noindex, follow"></head>')), '404.html')),
        ('404_missing_noindex_rejected', bool(metadata_errors(*parse_page(error_html), '404.html'))),
        ('valid_canonical_sitemap', not sitemap_errors([url], pages)),
        ('extensionless_sitemap_rejected', bool(sitemap_errors([url[:-5]], pages))),
        ('missing_sitemap_page_rejected', bool(sitemap_errors([], pages))),
        ('duplicate_sitemap_page_rejected', bool(sitemap_errors([url, url], pages))),
        ('missing_sitemap_url_rejected', bool(sitemap_errors([None], pages))),
        ('error_page_sitemap_rejected', bool(sitemap_errors([url, page_url('404.html')], {**pages, page_url('404.html'): {'relative': '404.html', 'noindex': False}}))),
        ('noindex_sitemap_rejected', bool(sitemap_errors([url], {url: {'relative': 'people/scar.html', 'noindex': True}}))),
        ('verification_file_sitemap_rejected', bool(sitemap_errors([url, page_url(GOOGLE_VERIFICATION)], pages))),
        ('verification_exact_proof', valid_google_proof(GOOGLE_VERIFICATION, b'google-site-verification: google450473d70e90c4cc.html')),
        ('verification_wrong_bytes_rejected', not valid_google_proof(GOOGLE_VERIFICATION, GOOGLE_PROOF + b'<p>reader</p>')),
        ('verification_wrong_filename_rejected', not valid_google_proof('people/scar.html', GOOGLE_PROOF)),
    ]
    return [{'name': name, 'status': 'PASS' if passed else 'FAIL'} for name, passed in checks]


def main():
    source = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=source / 'dist')
    parser.add_argument('--site', type=Path, default=source.parent)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--self-test-only', action='store_true')
    args = parser.parse_args()
    tests = self_tests() if args.self_test or args.self_test_only else []
    if args.self_test_only:
        report = {'status': 'PASS' if all(test['status'] == 'PASS' for test in tests) else 'FAIL'}
    else:
        try:
            report = verify(args.dist.resolve(), args.site.resolve())
        except (OSError, ValueError, ElementTree.ParseError) as error:
            report = {'status': 'FAIL', 'errorCount': 1, 'errors': [{'error': str(error)}]}
    if tests:
        report['selfTests'] = tests
        if any(test['status'] == 'FAIL' for test in tests):
            report['status'] = 'FAIL'
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
