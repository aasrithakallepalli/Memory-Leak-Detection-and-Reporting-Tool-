#!/usr/bin/env python3
"""report.py - turn a libmemleak log into a readable leak report.

Usage:
    python3 tools/report.py memleak.log [--exe ./prog] [--html out.html] [--json out.json]
                                        [--top N] [--fail-on-leak]

Log format (tab separated, written by src/memleak.c):
    L  size  ptr  frame...          one leaked block
    E  kind  ptr  frame...          an error event (invalid / double free)
    S  leaks bytes peak total allocs frees invalid     summary
    frame = address|module_base|module_path
"""
import argparse, html, json, os, subprocess, sys
from collections import OrderedDict, defaultdict


def parse(path):
    leaks, errors, summary = [], [], None
    with open(path) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if not parts or not parts[0]:
                continue
            if parts[0] == "S":
                k = ["leaks", "leaked_bytes", "peak_bytes", "total_bytes",
                     "allocs", "frees", "invalid_frees"]
                summary = dict(zip(k, map(int, parts[1:8])))
            elif parts[0] in ("L", "E"):
                frames = []
                for fr in parts[3:]:
                    a = fr.split("|", 2)
                    if len(a) == 3:
                        frames.append((int(a[0], 16), int(a[1], 16), a[2]))
                rec = {"ptr": parts[2], "frames": frames}
                if parts[0] == "L":
                    rec["size"] = int(parts[1]); leaks.append(rec)
                else:
                    rec["kind"] = parts[1]; errors.append(rec)
    return leaks, errors, summary


def elf_is_exec(path):
    """True for non-PIE executables (ET_EXEC): addr2line then wants absolute addresses."""
    try:
        with open(path, "rb") as f:
            h = f.read(18)
        return h[:4] == b"\x7fELF" and int.from_bytes(h[16:18], "little") == 2
    except OSError:
        return False


class Resolver:
    def __init__(self, exe_override=None):
        self.cache, self.exe = {}, exe_override

    def resolve_all(self, frame_set):
        by_mod = defaultdict(list)
        for fr in frame_set:
            by_mod[fr[2]].append(fr)
        for mod, frs in by_mod.items():
            real = mod
            if self.exe and os.path.basename(mod) == os.path.basename(self.exe):
                real = self.exe
            if not os.path.exists(real):
                for fr in frs: self.cache[fr] = ("??", "??", 0)
                continue
            absolute = elf_is_exec(real)
            addrs = [(fr[0] if absolute else fr[0] - fr[1]) - 1 for fr in frs]  # -1: return address
            try:
                out = subprocess.run(["addr2line", "-e", real, "-f", "-C"] + [hex(a) for a in addrs],
                                     capture_output=True, text=True, check=True).stdout.split("\n")
            except (OSError, subprocess.CalledProcessError):
                out = []
            for i, fr in enumerate(frs):
                try:
                    func, loc = out[2 * i], out[2 * i + 1]
                    file, _, line = loc.rpartition(":")
                    line = int(line.split()[0]) if line.split() and line.split()[0].isdigit() else 0
                except (IndexError, ValueError):
                    func, file, line = "??", "??", 0
                self.cache[fr] = (func, file, line)

    def get(self, fr):
        return self.cache.get(fr, ("??", "??", 0))


def user_stack(frames, res):
    """Frames from user code only (skip libmemleak and frames without debug info)."""
    out = []
    for fr in frames:
        if os.path.basename(fr[2]).startswith("libmemleak"):
            continue
        func, file, line = res.get(fr)
        if file in ("??", "") or line == 0:
            continue
        out.append({"function": func, "file": os.path.relpath(file) if os.path.isabs(file) else file, "line": line})
    return out


def analyse(leaks, errors, summary, exe):
    frames = {fr for r in leaks + errors for fr in r["frames"]
              if not os.path.basename(fr[2]).startswith("libmemleak")}
    res = Resolver(exe); res.resolve_all(frames)
    groups = OrderedDict()
    for r in leaks:
        st = user_stack(r["frames"], res)
        site = f'{st[0]["file"]}:{st[0]["line"]} in {st[0]["function"]}()' if st else "<unknown: compile with -g>"
        g = groups.setdefault(site, {"site": site, "count": 0, "bytes": 0, "stack": st, "sizes": set()})
        g["count"] += 1; g["bytes"] += r["size"]; g["sizes"].add(r["size"])
    glist = sorted(groups.values(), key=lambda g: -g["bytes"])
    for g in glist: g["sizes"] = sorted(g["sizes"])
    errs = []
    for e in errors:
        st = user_stack(e["frames"], res)
        errs.append({"kind": e["kind"], "ptr": e["ptr"], "stack": st,
                     "site": f'{st[0]["file"]}:{st[0]["line"]}' if st else "<unknown>"})
    if summary is None:  # program crashed before the destructor ran
        summary = {"leaks": len(leaks), "leaked_bytes": sum(r["size"] for r in leaks),
                   "peak_bytes": 0, "total_bytes": 0, "allocs": 0, "frees": 0, "invalid_frees": len(errs)}
    return {"summary": summary, "groups": glist, "errors": errs}


def text_report(d, top):
    s = d["summary"]; o = []
    o.append("=" * 60); o.append(" MEMORY LEAK REPORT"); o.append("=" * 60)
    o.append(f" Allocations: {s['allocs']}   Frees: {s['frees']}   Peak: {s['peak_bytes']} B   Total allocated: {s['total_bytes']} B")
    o.append(f" LEAKS: {s['leaks']} blocks, {s['leaked_bytes']} bytes   |   Invalid/double frees: {s['invalid_frees']}")
    o.append("-" * 60)
    if not d["groups"]: o.append(" No leaks detected.")
    for i, g in enumerate(d["groups"][:top], 1):
        o.append(f" #{i}  {g['bytes']} bytes in {g['count']} block(s)  [sizes: {', '.join(map(str, g['sizes']))}]")
        for j, fr in enumerate(g["stack"][:6]):
            o.append(f"      {'at' if j == 0 else 'by'} {fr['function']}() {fr['file']}:{fr['line']}")
    if d["errors"]:
        o.append("-" * 60); o.append(" INVALID / DOUBLE FREES")
        for e in d["errors"]:
            o.append(f"  free({e['ptr']}) at {e['site']}")
    o.append("=" * 60)
    return "\n".join(o)


def html_report(d):
    s = d["summary"]; e = html.escape
    rows = ""
    for i, g in enumerate(d["groups"], 1):
        stack = "<br>".join(f"{'at' if j == 0 else 'by'} {e(fr['function'])}() <code>{e(fr['file'])}:{fr['line']}</code>"
                            for j, fr in enumerate(g["stack"][:6]))
        pct = 100 * g["bytes"] / max(1, s["leaked_bytes"])
        rows += (f"<tr><td>{i}</td><td><b>{g['bytes']}</b> B<div class=bar><span style='width:{pct:.0f}%'></span></div></td>"
                 f"<td>{g['count']}</td><td>{e(', '.join(map(str, g['sizes'])))}</td><td class=st>{stack}</td></tr>")
    errs = "".join(f"<li><code>free({e_['ptr']})</code> at <code>{e(e_['site'])}</code></li>" for e_ in d["errors"])
    status = "ok" if s["leaks"] == 0 and s["invalid_frees"] == 0 else "bad"
    return f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8><title>Memory Leak Report</title>
<meta name=viewport content="width=device-width,initial-scale=1"><style>
:root{{--bg:#fff;--fg:#1d2430;--mut:#667;--card:#f4f6fa;--bd:#d9dee8;--bad:#c0392b;--ok:#1e8e4f;--acc:#2b6cb0}}
@media(prefers-color-scheme:dark){{:root{{--bg:#12161d;--fg:#e6e9ef;--mut:#9aa4b2;--card:#1b212b;--bd:#2c3542;--bad:#ff6b5c;--ok:#4cc38a;--acc:#6aa9ff}}}}
body{{font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:1000px;margin:2rem auto;padding:0 1rem}}
h1{{margin:0 0 .2rem}} .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.7rem;margin:1.2rem 0}}
.c{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:.8rem}} .c b{{display:block;font-size:1.5rem}} .c span{{color:var(--mut);font-size:.8rem}}
.ok b{{color:var(--ok)}} .bad b{{color:var(--bad)}}
table{{width:100%;border-collapse:collapse}} th,td{{text-align:left;padding:.5rem;border-bottom:1px solid var(--bd);vertical-align:top}}
th{{color:var(--mut);font-weight:600;font-size:.8rem;text-transform:uppercase}} .st{{font-size:.85rem}}
.bar{{height:6px;background:var(--bd);border-radius:3px;margin-top:4px}} .bar span{{display:block;height:100%;background:var(--bad);border-radius:3px}}
code{{background:var(--card);padding:1px 5px;border-radius:4px}} .tw{{overflow-x:auto}}
</style></head><body><h1>Memory Leak Report</h1><div style=color:var(--mut)>Generated by memleak-detector</div>
<div class=cards>
<div class="c {status}"><b>{s['leaks']}</b><span>leaked blocks</span></div>
<div class="c {status}"><b>{s['leaked_bytes']} B</b><span>leaked bytes</span></div>
<div class=c><b>{s['peak_bytes']} B</b><span>peak memory</span></div>
<div class=c><b>{s['allocs']} / {s['frees']}</b><span>allocs / frees</span></div>
<div class="c {'bad' if s['invalid_frees'] else 'ok'}"><b>{s['invalid_frees']}</b><span>invalid / double frees</span></div></div>
<h2>Leaks by call site</h2>{'<p>No leaks detected.</p>' if not rows else f'<div class=tw><table><tr><th>#<th>Bytes<th>Blocks<th>Sizes<th>Call stack</tr>{rows}</table></div>'}
{f'<h2>Invalid / double frees</h2><ul>{errs}</ul>' if errs else ''}
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log"); ap.add_argument("--exe", help="path to the target binary (for addr2line)")
    ap.add_argument("--html"); ap.add_argument("--json"); ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--fail-on-leak", action="store_true", help="exit 1 if any leak/invalid free is found")
    a = ap.parse_args()
    leaks, errors, summary = parse(a.log)
    d = analyse(leaks, errors, summary, a.exe)
    print(text_report(d, a.top))
    if a.json: json.dump(d, open(a.json, "w"), indent=2)
    if a.html: open(a.html, "w").write(html_report(d))
    if a.fail_on_leak and (d["summary"]["leaks"] or d["summary"]["invalid_frees"]): sys.exit(1)


if __name__ == "__main__":
    main()
