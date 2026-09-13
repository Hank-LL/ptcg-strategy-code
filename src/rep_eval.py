import os, statistics, sys
from cg.game import battle_start, battle_select, battle_finish
from cg.api import to_observation_class
import generic_heuristic as gh, opponent_agents as oa
from policy_net import load_policy, encode_observation

FUUDIN_DECK=os.environ.get("EVAL_DECK","fuudin_deck.csv")
def read_deck(p): return [int(x) for x in open(p).read().split("\n") if x.strip()][:60]

def make_agent(w):
    pol=load_policy(w)
    def ag(obs):
        if obs.get("select") is None: return read_deck(FUUDIN_DECK)
        try:
            sel=obs["select"]; n=len(sel["option"])
            enc=encode_observation(obs, obs["current"]["yourIndex"])
            lo=sel.get("minCount") or 1; hi=sel.get("maxCount") or 1
            k=min(max(lo,1),hi,n)
            idx=[i for i in pol.choose_k(enc,n) if 0<=i<n][:k]
            return idx or gh.agent(obs)
        except Exception: return gh.agent(obs)
    return ag

def run(name, w, reps, n):
    opps=oa.load_opponents(gh.agent)
    fu=next(o for o in opps if "alakazam" in o.name.lower())
    deck=read_deck(FUUDIN_DECK); ag=make_agent(w); rates=[]
    for r in range(reps):
        win=g=0
        for i in range(n):
            fu.reset_state()
            d0,d1=(deck,fu.deck) if i%2==0 else (fu.deck,deck)
            a0,a1=(ag,fu) if i%2==0 else (fu,ag)
            obs,sd=battle_start(d0,d1)
            if obs is None: continue
            A=[a0,a1]; s=0
            try:
                while obs["current"]["result"]==-1 and s<3000:
                    obs=battle_select(A[obs["current"]["yourIndex"]](obs)); s+=1
                win += (obs["current"]["result"]==(0 if i%2==0 else 1)); g+=1
            finally: battle_finish()
        rates.append(win/g*100)
    m=statistics.mean(rates); se=statistics.pstdev(rates)/(len(rates)**0.5)
    print(f"  {name:16s} 対フーディン {m:5.1f}% ±{se:.1f}  {['%.0f'%x for x in rates]}")
    return m

if __name__=="__main__":
    reps=int(sys.argv[1]); n=int(sys.argv[2])
    run("bc5(70M)", "/tmp/w_bc5.pt", reps, n)
    run("bc6(100.6M)", "/tmp/w_bc6f.pt", reps, n)
