"""ワナイダーの改良測定(強い相手のみ)。"""
import collections, importlib, statistics, sys
from cg.game import battle_start, battle_select, battle_finish
from cg.api import to_observation_class, OptionType
import generic_heuristic as gh, wanaider_heuristic as wh, opponent_agents as oa

POOL = "../meta/top_decks"
def read_deck(p): return [int(x) for x in open(p).read().split("\n") if x.strip()][:60]

def build_opponents():
    opps = []
    ext = oa.load_opponents(gh.agent)
    fu = next((o for o in ext if "alakazam" in o.name.lower()), None)
    if fu: opps.append(fu)
    for mod, dk in [("alakazam_heuristic", f"{POOL}/deck_fuudin_top.csv"),
                    ("grimmsnarl_heuristic", f"{POOL}/deck_grimmsnarl.csv"),
                    ("crustle_heuristic", f"{POOL}/deck_iwaparesu.csv")]:
        try:
            m = importlib.import_module(mod)
            f = (lambda mm: (lambda o: mm.agent(o)))(m)
            f.deck = read_deck(dk); f.name = mod
            f.reset_state = (lambda mm: (lambda: mm.reset_state() if hasattr(mm, "reset_state") else None))(m)
            opps.append(f)
        except Exception as e:
            print("skip", mod, e)
    return opps

def run(label, deck_path, opps, reps=5, n=40, detail=False):
    deck = read_deck(deck_path); rates=[]; wide=[]; per=collections.defaultdict(lambda:[0,0])
    for r in range(reps):
        w=g=0
        for opp in opps:
            for i in range(n):
                wh.reset_state()
                if hasattr(opp,"reset_state"): opp.reset_state()
                ms=i%2
                d0,d1=(deck,opp.deck) if ms==0 else (opp.deck,deck)
                a0,a1=(wh.agent,opp) if ms==0 else (opp,wh.agent)
                obs,sd=battle_start(d0,d1)
                if obs is None: continue
                A=[a0,a1]; s=0
                try:
                    while obs["current"]["result"]==-1 and s<3000:
                        pl=obs["current"]["yourIndex"]
                        if pl==ms and detail:
                            sel=obs["select"]; a=wh.agent(obs)
                            if sel.get("context")==0 and sel.get("option") and sel["option"][a[0]].get("type")==OptionType.ATTACK:
                                o=to_observation_class(obs); me=o.current.players[ms]
                                wide.append(sum(1 for c in list(me.active or [])+list(me.bench or []) if c and c.id in wh.ROCKET_POKEMON))
                            obs=battle_select(a)
                        else:
                            obs=battle_select(A[pl](obs))
                        s+=1
                    win = to_observation_class(obs).current.result==ms
                    w+=win; g+=1; per[opp.name][0]+=win; per[opp.name][1]+=1
                finally: battle_finish()
        rates.append(w/g*100)
    m=statistics.mean(rates); se=statistics.pstdev(rates)/(len(rates)**0.5)
    extra=f"  攻撃時盤面 {statistics.mean(wide):.2f}" if wide else ""
    print(f"  {label:26s} {m:5.1f}% ±{se:.1f}{extra}")
    if detail:
        for k,(a,b) in per.items(): print(f"      {k:24s} {a/b*100:5.1f}%")
    return m

if __name__=="__main__":
    reps=int(sys.argv[1]) if len(sys.argv)>1 else 5
    n=int(sys.argv[2]) if len(sys.argv)>2 else 40
    opps=build_opponents()
    print("=== 展開強化(WIDE_ENOUGH=5 + たね最優先)の効果 ===")
    for dk,name in [(f"{POOL}/deck_wanaider_top.csv","現行デッキ"),(f"{POOL}/deck_wanaider_top2.csv","上位デッキ")]:
        run(f"{name}", dk, opps, reps, n, detail=True)
