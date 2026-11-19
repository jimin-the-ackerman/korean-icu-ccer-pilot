import json, glob, os, re, subprocess, sys
from collections import Counter

AUDIO = glob.glob("data/audio/*.mp3")
GOLD = [f for f in glob.glob("data/generated_text/*.json") if not f.endswith("generation_log.json")]
STT = [f for f in glob.glob("data/stt_transcripts/*.json") if not f.endswith("generation_log.json")]
SCEN = glob.glob("data/scenarios/scenario_*.json")

ids = lambda files, ext: {os.path.basename(f)[:-len(ext)] for f in files}
a, g, s = ids(AUDIO, ".mp3"), ids(GOLD, ".json"), ids(STT, ".json")
print("audio/gold/stt 개수:", len(a), len(g), len(s))
print("audio-gold 불일치:", sorted(a ^ g)[:10])
print("audio-stt 불일치:", sorted(a ^ s)[:10])

pat = re.compile(r"^(scenario_\d+)_(.+)$")
pairs = Counter(pat.match(x).groups() for x in a if pat.match(x))
print("중복 조합:", [k for k, v in pairs.items() if v > 1])
scen_ids = {json.load(open(f))["scenario_id"] for f in SCEN}
print("scaffold 없는 scenario:", sorted({k[0] for k in pairs} - scen_ids))
print("register별 개수:", dict(Counter(k[1] for k in pairs)))

bad = [f for f in GOLD if json.load(open(f))["sample_id"] != os.path.basename(f)[:-5]]
print("파일명-내부ID 불일치:", bad[:10])

print("python:", sys.version.split()[0])
print("git commit:", subprocess.getoutput("git rev-parse HEAD"))
print("working tree 변경:", subprocess.getoutput("git status --porcelain | head -5") or "없음")
