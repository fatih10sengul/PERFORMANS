#!/usr/bin/env python3
"""TFF'den yeni Fethiyespor U19 maçlarını okuyup index.html içindeki MATCH_SEED listesine ekler.
Lig: U19 Gelişim Ligi 9. Grup (grupID=3895). Hata olursa hiçbir dosyayı değiştirmez ve 1 koduyla çıkar."""
import re, sys, json, subprocess, datetime, urllib.request, html as H

BASE = 'https://www.tff.org/Default.aspx'
GRUP = 3895
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
FIX = ('Default.aspx?pageID=1751&grupID=%d&hafta=%d')


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'tr-TR,tr;q=0.9'})
    with urllib.request.urlopen(req, timeout=40) as r:
        b = r.read()
    return dec(b)


def dec(b):
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return b.decode('cp1254', errors='replace')


def norm(s):
    return re.sub(r'\s+', ' ', H.unescape(s)).strip()


def tr_title(s):
    out = []
    for w in norm(s).split(' '):
        if '.' in w:
            out.append(w.upper())
            continue
        lw = w.replace('İ', 'i').replace('I', 'ı').lower()
        if not lw:
            continue
        f = lw[0]
        f = 'İ' if f == 'i' else ('I' if f == 'ı' else f.upper())
        out.append(f + lw[1:])
    return ' '.join(out)


def is_us(name):
    return re.search(r'FETH.{0,2}YESPOR', norm(name).upper()) is not None


def parse_fixture(h):
    """[(macId, date 'YYYY-MM-DD', home, away, score or None)]"""
    rows = []
    for ch in re.split(r'<tr', h):
        if 'lblSkor' not in ch:
            continue
        t1 = re.search(r'lblTakim1"[^>]*>([^<]*)<', ch)
        t2 = re.search(r'lblTakim2"[^>]*>([^<]*)<', ch)
        sk = re.search(r'lblSkor"[^>]*macId=(\d+)"[^>]*>([^<]*)<', ch) or re.search(r'macId=(\d+)[^>]*lblSkor[^>]*>([^<]*)<', ch)
        d = re.search(r'(\d\d)\.(\d\d)\.(\d{4})', ch)
        if not (t1 and t2 and sk and d):
            continue
        sc = norm(sk.group(2))
        sc = sc if re.fullmatch(r'\d+\s*-\s*\d+', sc) else None
        rows.append((int(sk.group(1)), '%s-%s-%s' % (d.group(3), d.group(2), d.group(1)), norm(t1.group(1)), norm(t2.group(1)), sc.replace(' ', '') if sc else None))
    return rows


def minute(s):
    m = re.search(r'(\d+)(?:\+\d+)?\.?\s*dk', s)
    return int(m.group(1)) if m else None


SECS = ['rptKadrolar', 'rptYedekler', 'rptTeknikKadro', 'rptGoller', 'rptKartlar', 'rptCikanlar', 'rptGirenler']


def sections(h, team):
    if team == 1:
        e = h.find('grdTakim2_')
        if e > 0:
            h = h[:e]
    pos = []
    for s in SECS:
        i = h.find('grdTakim%d_%s_ctl00' % (team, s))
        if i >= 0:
            pos.append((i, s))
    pos.sort()
    out = {}
    for k, (i, s) in enumerate(pos):
        j = pos[k + 1][0] if k + 1 < len(pos) else len(h)
        out[s] = h[i:j]
    # son bölüm sayfa sonuna kadar uzar: ikinci takımın bölümlerine taşmasın
    return out


def anchors(seg):
    return [(int(a), norm(n)) for a, n in re.findall(r'kisiId=(\d+)"[^>]*>([^<]*)</a>', seg)]


def parse_team(h, team):
    s = sections(h, team)
    if 'rptKadrolar' not in s:
        raise ValueError('kadro bölümü yok (takım %d)' % team)
    starters = anchors(s['rptKadrolar'])
    if len(starters) != 11:
        raise ValueError('ilk 11 sayısı %d (takım %d)' % (len(starters), team))
    names = {k: v for k, v in starters}
    for k, v in anchors(s.get('rptYedekler', '')):
        names[k] = v
    goals, own = {}, {}
    for m in re.finditer(r'kisiId=(\d+)"[^>]*>([^<]*)</a>', s.get('rptGoller', '')):
        kid, txt = int(m.group(1)), norm(m.group(2))
        if re.search(r'\(\s*K\s*\)', txt):
            own[kid] = own.get(kid, 0) + 1
        else:
            goals[kid] = goals.get(kid, 0) + 1
    yel, red = {}, {}
    for m in re.finditer(r'<img[^>]*alt="([^"]*)"[^>]*/?>\s*(?:&nbsp;)?\s*<a[^>]*kisiId=(\d+)"[^>]*>[^<]*</a>\s*<span[^>]*>([^<]*)</span>', s.get('rptKartlar', '')):
        alt, kid, dk = norm(m.group(1)).lower(), int(m.group(2)), minute(m.group(3))
        if 'k' in alt and 'rm' in alt:  # Kırmızı
            red[kid] = dk
        else:
            yel[kid] = yel.get(kid, 0) + 1
    outs = {}
    for m in re.finditer(r'kisiId=(\d+)"[^>]*>[^<]*</a>\s*(?:&nbsp;|\s)*<span[^>]*>([^<]*)</span>', s.get('rptCikanlar', '')):
        outs[int(m.group(1))] = minute(m.group(2))
    ins = []
    for m in re.finditer(r'kisiId=(\d+)"[^>]*>[^<]*</a>\s*(?:&nbsp;|\s)*<span[^>]*>([^<]*)</span>', s.get('rptGirenler', '')):
        ins.append((int(m.group(1)), minute(m.group(2))))
    for kid in list(outs) + [k for k, _ in ins]:
        if kid not in names:
            raise ValueError('değişiklikte bilinmeyen oyuncu %s' % kid)
    for kid, dk in list(outs.items()) + ins:
        if dk is None:
            raise ValueError('dakika okunamadı')
    return dict(starters=[k for k, _ in starters], names=names, goals=goals, own=own, yel=yel, red=red, outs=outs, ins=ins)


def build_players(t):
    def end(kid):
        o = t['outs'].get(kid)
        r = t['red'].get(kid)
        c = [x for x in (o, r) if x is not None]
        return min(c) if c else 90
    rows = []
    for kid in t['starters']:
        rows.append([t['names'][kid], 1, 0, end(kid), t['goals'].get(kid, 0), t['yel'].get(kid, 0)])
    subs = sorted(t['ins'], key=lambda x: x[1])
    for kid, dk in subs:
        rows.append([t['names'][kid], 0, dk, end(kid), t['goals'].get(kid, 0), t['yel'].get(kid, 0)])
    return rows


def parse_match(h, home_us, gf, ga):
    """h: maç sayfası. home_us: Fethiyespor ev sahibi mi. Skorla tutarsızsa ValueError."""
    t = {1: parse_team(h, 1), 2: parse_team(h, 2)}
    us, them = (1, 2) if home_us else (2, 1)
    f = sum(t[us]['goals'].values()) + sum(t[them]['own'].values())
    a = sum(t[them]['goals'].values()) + sum(t[us]['own'].values())
    if (f, a) != (gf, ga):
        raise ValueError('gol sayısı skorla uyuşmuyor (kadro %d-%d, skor %d-%d)' % (f, a, gf, ga))
    return build_players(t[us])


def js_str(s):
    return "'" + s.replace('\\', '\\\\').replace("'", "\\'") + "'"


def js_entry(mid, d, opp, home, gf, ga, rows):
    def r(x):
        return '[%s,%d,%d,%d,%d,%d]' % (js_str(x[0]), x[1], x[2], x[3], x[4], x[5])
    st = ','.join(r(x) for x in rows if x[1] == 1)
    sb = ','.join(r(x) for x in rows if x[1] == 0)
    return "{tff:%d,d:%s,opp:%s,h:%d,gf:%d,ga:%d,p:[\n%s%s]}" % (mid, js_str(d), js_str(opp), home, gf, ga, st, (',\n' + sb) if sb else '')


def main(index='index.html', sw='sw.js', today=None, fetcher=None, dry=False):
    fetcher = fetcher or fetch
    today = today or datetime.date.today().isoformat()
    src = open(index, encoding='utf-8').read()
    a = src.index('var MATCH_SEED=[')
    b = src.index('function seedMatches')
    end = src.rfind('];', a, b)
    block = src[a:end + 2]
    have = set(int(x) for x in re.findall(r'\{tff:(\d+)', block))
    new, problems, empty = [], [], 0
    for wk in range(1, 46):
        rows = parse_fixture(fetcher('https://www.tff.org/' + FIX % (GRUP, wk)))
        if not rows:
            empty += 1
            if empty >= 3:
                break
            continue
        empty = 0
        for mid, d, t1, t2, sc in rows:
            if not (is_us(t1) or is_us(t2)) or mid in have or not sc or d > today:
                continue
            home = 1 if is_us(t1) else 0
            gh, ga_ = [int(x) for x in sc.split('-')]
            gf, ga = (gh, ga_) if home else (ga_, gh)
            try:
                mh = fetcher('%s?pageId=29&macId=%d' % (BASE, mid))
                pl = parse_match(mh, home, gf, ga)
            except Exception as e:
                problems.append('macId %d (%s, hafta %d): %s' % (mid, d, wk, e))
                continue
            opp = tr_title(t2 if home else t1)
            new.append((d, js_entry(mid, d, opp, home, gf, ga, pl), '%s %s %d-%d (%d oyuncu)' % (d, opp, gf, ga, len(pl))))
    new.sort(key=lambda x: x[0])
    for p in problems:
        print('UYARI:', p)
    if not new:
        print('Yeni maç yok.' if not problems else 'Eklenebilen maç yok.')
        return 1 if problems else 0
    add = ''.join(',\n' + e for _, e, _ in new)
    # son nesnenin kapanışından hemen sonra ekle
    body = block[:-2].rstrip()
    out = src[:a] + body + add + '\n];' + src[end + 2:]
    # doğrulama
    js = block_for_check(out)
    chk = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if chk.returncode != 0:
        print('DOĞRULAMA HATASI:', chk.stderr[-400:])
        return 1
    print(chk.stdout.strip())
    if dry:
        for _, e, s in new:
            print(e)
        return 0
    open(index, 'w', encoding='utf-8').write(out)
    s = open(sw, encoding='utf-8').read()
    m = re.search(r'pp-v(\d+)', s)
    if m:
        s = s.replace(m.group(0), 'pp-v%d' % (int(m.group(1)) + 1), 1)
        open(sw, 'w', encoding='utf-8').write(s)
    for _, _, s_ in new:
        print('EKLENDI:', s_)
    return 1 if problems else 0


def block_for_check(src):
    a = src.index('var MATCH_SEED=[')
    b = src.index('function seedMatches')
    end = src.rfind('];', a, b)
    blk = src[a:end + 2]
    return blk + ";var ids={};MATCH_SEED.forEach(function(m){if(ids[m.tff])throw new Error('tekrar '+m.tff);ids[m.tff]=1;var g=m.p.reduce(function(s,r){return s+r[4]},0);if(!Array.isArray(m.p)||m.p.length<11)throw new Error('kadro '+m.tff);});console.log('Dogrulama tamam, maç sayısı: '+MATCH_SEED.length);"


if __name__ == '__main__':
    sys.exit(main())
