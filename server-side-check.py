#!/usr/bin/env python3
"""Dedicated-server safety check: finds references from a mod's common (both-side) classes to Minecraft code
that only exists on the client: @SideOnly(CLIENT) members (resolved up the class hierarchy, with a mixin's own
members looked up in its target class) and net.minecraft.client classes. On a dedicated server such a reference is
a NoSuchMethodError or NoClassDefFoundError at the moment it runs; inside a packet handler FML answers with
"A fatal error has occured, this connection is terminated" and the client is kicked.

Reads the compiled classes, so build first (./gradlew build or a runClient/runServer). Scans the Java files changed
or added on the branch relative to the main branch (origin's default, else main or master; --base names another),
except client packages and *Client* classes; members annotated
@SideOnly(CLIENT) are skipped since FML strips them on the server. Guarded uses are listed too (an "instanceof" of
a client class behind world.isRemote is fine, since classes resolve lazily); judge each line.

Usage: ./server-side-check.py                (branch files)
       ./server-side-check.py --base REF     (files changed since REF)
       ./server-side-check.py --stdin        (file list on stdin, paths relative to src/main/java)"""
import os, re, subprocess, sys, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
MCJAR = os.path.join(ROOT, "build/rfg/recompiled_minecraft-1.7.10.jar")
CLASSES = os.path.join(ROOT, "build/classes/java/main")
MC_PREFIXES = ("net.minecraft.", "net.minecraftforge.", "cpw.mods.fml.")

def is_common(path):
    parts = path.split("/")
    name = parts[-1][:-5]
    return "client" not in parts and "Client" not in name

def git(*args):
    return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True, text=True)

def base_ref():
    """--base REF, else origin's default branch, else main or master."""
    if "--base" in sys.argv:
        return sys.argv[sys.argv.index("--base") + 1]
    head = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD").stdout.strip()
    for ref in ([head] if head else []) + ["main", "master"]:
        if git("rev-parse", "--verify", "--quiet", ref).returncode == 0:
            return ref
    sys.exit("no main or master branch to compare with: name one with --base REF")

def branch_files():
    out = []
    for cmd in (["git", "diff", "--name-only", base_ref() + "...HEAD"], ["git", "diff", "--name-only"],
                ["git", "ls-files", "--others", "--exclude-standard"]):
        out += subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    return sorted({l.replace("src/main/java/", "", 1) for l in out if l.startswith("src/main/java/") and l.endswith(".java")})

for path in (MCJAR, CLASSES):
    if not os.path.exists(path):
        sys.exit(f"missing {path}: build first")
listed = [l.strip() for l in sys.stdin] if "--stdin" in sys.argv else branch_files()
targets, skipped = [], []
for f in listed:
    if not f.endswith(".java"):
        continue
    if not is_common(f):
        skipped.append(f)
        continue
    base = f[:-5]
    d, stem = os.path.join(CLASSES, os.path.dirname(base)), os.path.basename(base)
    if os.path.isdir(d):
        for cf in sorted(os.listdir(d)):
            if cf == stem + ".class" or (cf.startswith(stem + "$") and cf.endswith(".class")):
                targets.append(os.path.join(d, cf))

def javap(args):
    return subprocess.run(["javap", "-c", "-p", "-v"] + args, capture_output=True, text=True).stdout

def strip_generics(s):
    out, depth = [], 0
    for ch in s:
        if ch == "<": depth += 1
        elif ch == ">": depth -= 1
        elif depth == 0: out.append(ch)
    return "".join(out)

HEADER = re.compile(r"^(?:(?:public|final|abstract|interface|class|enum|static|strictfp) )*(?:class|interface|enum) ([\w.$]+)(?: extends ([\w.$, ]+))?(?: implements ([\w.$, ]+))?")
MEMBER = re.compile(r"^  [^ ].*;$")
REF = re.compile(r"// (Method|InterfaceMethod|Field|class) (\S+)")

def parse_classes(text):
    """javap -v output -> {class name: info}"""
    classes, cur = {}, None
    for raw in text.split("\n"):
        line = raw.rstrip()
        m = HEADER.match(strip_generics(line)) if line and not line.startswith(" ") else None
        if m and not line.startswith("Classfile") and "(" not in line:
            cur = {"name": m.group(1), "super": (m.group(2) or "").split(", ")[0] or None,
                   "ifaces": [i for i in (m.group(3) or "").split(", ") if i],
                   "client": False, "client_members": set(), "members": set(), "mixin": None,
                   "refs": [], "method": None, "_member": None, "_side": 0}
            classes[cur["name"]] = cur
            continue
        if cur is None:
            continue
        if MEMBER.match(line) and "descriptor" not in line:
            cur["_member"] = line.strip()
            cur["method"] = cur["_member"]
            continue
        if line.startswith("    descriptor: ") and cur["_member"] is not None:
            name = cur["_member"].split("(")[0].split(" ")[-1] if "(" in cur["_member"] else cur["_member"].rstrip(";").split(" ")[-1]
            desc = line.split(": ", 1)[1]
            cur["_key"] = (name, desc)
            cur["members"].add(cur["_key"])
            continue
        if "cpw.mods.fml.relauncher.SideOnly(" in line:
            # member-level vs class-level: javap indents a member's annotation 8 spaces, the class's 4
            cur["_side"] = 2 if line.startswith("        ") else 1
            continue
        if cur["_side"] and "value=" in line:
            if "CLIENT" in line:
                if cur["_side"] == 2 and cur.get("_key"): cur["client_members"].add(cur["_key"])
                elif cur["_side"] == 1: cur["client"] = True
            cur["_side"] = 0
            continue
        mm = re.search(r"org\.spongepowered\.asm\.mixin\.Mixin\(", line)
        if mm:
            cur["_mixin"] = True
            continue
        if cur.get("_mixin") and "value=" in line:
            cm = re.search(r"class ([\w.$]+)", line)
            if cm: cur["mixin"] = cm.group(1)
            cur["_mixin"] = False
            continue
        r = REF.search(line)
        if r and cur["method"]:
            op = line.split()[1] if re.match(r"^\s+\d+: ", line) else "?"
            cur["refs"].append((cur["method"], cur.get("_key"), op, r.group(1), r.group(2)))
    return classes

print(f"reading {len(targets)} class files of the branch's common classes...", file=sys.stderr)
mod = parse_classes(javap(targets))
mod = {k: v for k, v in mod.items() if not v["client"]}

# Minecraft classes needed: referenced owners, mixin targets, then their supertypes.
mc, pending = {}, set()
def want(name):
    if name and name.startswith(MC_PREFIXES) and name not in mc: pending.add(name)
for info in mod.values():
    want(info["mixin"])
    for _, _, _, kind, ref in info["refs"]:
        if kind == "class":
            want(ref.replace("/", "."))
        else:
            owner = ref.split(".")[0].replace("/", ".") if "." in ref.split(":")[0] else None
            want(owner)
while pending:
    batch = sorted(pending); pending.clear()
    print(f"reading {len(batch)} Minecraft classes from the dev jar...", file=sys.stderr)
    parsed = parse_classes(subprocess.run(["javap", "-p", "-v", "-cp", MCJAR] + batch, capture_output=True, text=True).stdout)
    for name in batch:
        mc[name] = parsed.get(name)
    for p in parsed.values():
        want(p["super"]); [want(i) for i in p["ifaces"]]

def declaring(owner, key):
    seen, todo = set(), [owner]
    while todo:
        c = todo.pop(0)
        if c in seen or c not in mc or mc[c] is None: continue
        seen.add(c)
        if key in mc[c]["members"]: return c
        todo += [mc[c]["super"]] + mc[c]["ifaces"]
    return None

def client_class(name):
    return name.startswith("net.minecraft.client.") or (mc.get(name) is not None and mc[name]["client"])

findings = collections.OrderedDict()
for cname, info in sorted(mod.items()):
    for method, key, op, kind, ref in info["refs"]:
        if key in info["client_members"]:      # FML strips @SideOnly(CLIENT) members from mod classes on the server
            continue
        if kind == "class":
            name = ref.replace("/", ".")
            if client_class(name):
                findings.setdefault(cname, []).append(f"{op} {name}  [client-only class]  in {method}")
            continue
        head, desc = ref.split(":", 1)
        if "." in head:
            owner, mname = head.rsplit(".", 1)
            owner = owner.replace("/", ".")
        else:
            owner, mname = cname, head
        if owner in mod or owner == cname:      # its own class or another of the mod's: a mixin's own members live in the target
            owner = (mod.get(owner) or info).get("mixin") or owner
            if not owner.startswith(MC_PREFIXES): continue
        if not owner.startswith(MC_PREFIXES): continue
        if client_class(owner):
            findings.setdefault(cname, []).append(f"{op} {owner}.{mname}  [member of a client-only class]  in {method}")
            continue
        decl = declaring(owner, (mname, desc))
        if decl and (mname, desc) in mc[decl]["client_members"]:
            findings.setdefault(cname, []).append(f"{op} {owner}.{mname}{desc}  [@SideOnly(CLIENT) in {decl}]  in {method}")

print(f"scanned {len(mod)} common classes from {len(targets)} class files; skipped {len(skipped)} client-named sources; {len(mc)} Minecraft classes read")
print(f"{sum(len(v) for v in findings.values())} references to client-only code:\n")
for cname, items in findings.items():
    print(cname)
    for it in items: print("   ", it)
