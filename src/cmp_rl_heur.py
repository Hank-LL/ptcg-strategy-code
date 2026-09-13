"""RL(上位デッキ)とヒューリスティック(上位デッキ)を、同じ相手・同じデッキで反復比較。"""
import importlib, os, statistics, sys
from cg.game import battle_start, battle_select, battle_finish
from cg.api import to_observation_class
import generic_heuristic as gh, opponent_agents as oa
from policy_net import load_policy, encode_observation

POOL="../meta/top_decks"
DECK=f"{POOL}/deck_fuudin_top.csv"
def rd(p): return [int(x) for x in open(p).read().split("\n") if x.strip()][:60]

def rl_agent(weights):
    pol=load_policy(weights)
    def ag(obs):
        if obs.get("select") is None: return rd(DECK)
        try:
            sel=obs["select"]; n=len(sel["option"])
            enc=encode_observation(obs, obs["current"]["yourIndex"])
            lo=sel.get("minCount") or 1; hi=sel.get("maxCount") or 1
            k=min(max(lo,1),hi,n)
            idx=[i for i in pol.choose_k(enc,n) if 0<=i<n][:k]
            return idx or gh.agent(obs)
        except Exception: return gh.agent(obs)
    return ag

def build_opponents():
    opps=[]
    ext=oa.load_opponents(gh.agent)
    fu=next((o for o in ext if "alakazam" in o.name.lower()), None)
    if fu: opps.append(fu)
    for mod,dk in [("grimmsnarl_heuristic",f"{POOL}/deck_grimmsnarl.csv"),
                   ("crustle_heuristic",f"{POOL}/deck_iwaparesu.csv"),
                   ("wanaider_heuristic",f"{POOL}/deck_wanaider_top2.csv")]:
        try:
            m=importlib.import_module(mod)
            f=(lambda mm:(lambda o: mm.agent(o)))(m)
            f.deck=rd(dk); f.name=mod
            f.reset_state=(lambda mm:(lambda: mm.reset_state() if hasattr(mm,"reset_state") else None))(m)
            opps.append(f)
        except Exception as e: print("skip",mod,e)
    return opps

def run(label, agent, reset, opps, reps, n):
    deck=rd(DECK); rates=[]; per={}
    for r in range(reps):
        w=g=0
        for opp in opps:
            pw=pg=0
            for i in range(n):
                reset()
                if hasattr(opp,"reset_state"): opp.reset_state()
                ms=i%2
                d0,d1=(deck,opp.deck) if ms==0 else (opp.deck,deck)
                a0,a1=(agent,opp) if ms==0 else (opp,agent)
                obs,sd=battle_start(d0,d1)
                if obs is None: continue
                A=[a0,a1]; s=0
                try:
                    while obs["current"]["result"]==-1 and s<3000:
                        obs=battle_select(A[obs["current"]["yourIndex"]](obs)); s+=1
                    win=to_observation_class(obs).current.result==ms
                    w+=win; g+=1; pw+=win; pg+=1
                finally: battle_finish()
            per.setdefault(opp.name,[0,0])
            per[opp.name][0]+=pw; per[opp.name][1]+=pg
        rates.append(w/g*100)
    m=statistics.mean(rates); se=statistics.pstdev(rates)/(len(rates)**0.5)
    print(f"  {label:22s} {m:5.1f}% ±{se:.1f}  {['%.0f'%x for x in rates]}")
    for k,(a,b) in per.items(): print(f"      {k:24s} {a/b*100:5.1f}%")
    return m

if __name__=="__main__":
    reps=int(sys.argv[1]); n=int(sys.argv[2])
    opps=build_opponents()
    import alakazam_heuristic as ah
    print("=== 上位デッキで RL vs ヒューリスティック ===")
    run("RL(130M)", rl_agent("policy_weights_ppo_top.pt"), lambda: None, opps, reps, n)
    run("ヒューリスティック", ah.agent, ah.reset_state, opps, reps, n)
