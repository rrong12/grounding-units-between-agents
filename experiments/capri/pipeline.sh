#!/bin/zsh
# Stage-selectable pipeline. Launch from a plain terminal, for example on a second CLI account:
#   source harness_env.sh && RESULTS_TAG=_heldout STAGES="E2" ./pipeline.sh
# RESULTS_TAG keeps each account's rows in separate files (results_e2e_heldout.jsonl, ...): the CLI injects the account's own
# email into every run, so run whole stages on one account and never split a results table across accounts.
# Every runner is resumable; usage-limit errors -> sleep 30 min and retry; other errors -> retry up to 3 times, then move on.
cd "$(dirname "$0")"
[ -n "$HARNESS_NOTE" ] || { echo "run: source harness_env.sh first"; exit 1; }
export RESULTS_TAG=${RESULTS_TAG:-}
STAGES=${STAGES:-"E1 E2 B C D F G"}
mkdir -p logs
O=claude-opus-5-5; S=claude-sonnet-5; H=claude-haiku-4-5-20251001; F=claude-fable-5-1; G=gpt-6.1-sol
E=results_e2e$RESULTS_TAG.jsonl; A=results_ablation$RESULTS_TAG.jsonl; P=results_probe$RESULTS_TAG.jsonl
LOG=logs/pipeline$RESULTS_TAG.log
log() { echo "[$(date '+%F %T')] $*" | tee -a $LOG; }
want() { [[ " $STAGES " == *" $1 "* ]]; }
step() {  # step NAME RESULT_FILE CMD...
  local name=$1 file=$2; shift 2; local other=0 n0 out nerr
  for try in {1..60}; do
    n0=$([ -f $file ] && wc -l < $file || echo 0)
    log "$name: pass $try"
    out=$("$@" 2>&1 | tee -a logs/$name$RESULTS_TAG.log | grep '^errors:' | tail -1)
    nerr=$(echo "$out" | awk '{print $2}'); nerr=${nerr:-1}
    log "$name: ${out:-runner exited without a summary}"
    [ "$nerr" -eq 0 ] && return 0
    if tail -n +$((n0 + 1)) $file 2>/dev/null | grep -q "session limit"; then log "$name: usage limit hit; sleeping 30 min"; sleep 1800
    else other=$((other + 1)); [ $other -ge 3 ] && { log "$name: giving up after 3 passes with non-limit errors"; return 1; }; sleep 60; fi
  done
}
E12="none,explicit,pcot,typed,selfunc,explicit+inferred+resolver+hybrid,explicit+inferred+resolver,ground+xcheck+readback,ground,ground+xcheck,xcheck+readback,stated"
E9="none,explicit,pcot,typed,selfunc,explicit+inferred+resolver+hybrid,explicit+inferred+resolver,ground+xcheck+readback,stated"
MAIN4="none,explicit+inferred+resolver,explicit+inferred+resolver+hybrid,ground+xcheck+readback"
INJ="inject:bare,inject:own,inject:wrong,inject:hedged"
FACT="none,explicit,card,resolver,generic,inferred+resolver,explicit+inferred+resolver,explicit+card+resolver"
SAMEA="none,explicit+card+resolver,explicit+inferred+resolver"

log "start at git $(git rev-parse --short HEAD); stages: $STAGES; tag: '${RESULTS_TAG}'; $(claude --version 2>/dev/null)"
if want E1; then for m in $O $S; do step E1_$m $E python3 run_e2e.py $m $m "$E12" --split dev --step 2 --workers 4; done; fi
if want E2; then
  for m in $O $S $H; do step E2_$m $E python3 run_e2e.py $m $m "$E9" --split heldout --workers 4; done
  for m in $O $S $H; do step E2same_$m $E python3 run_e2e.py $m $m "$MAIN4" --split heldout --same --step 2 --workers 4; done
fi
if want B; then
  step B_main results_frontier_$S$RESULTS_TAG.jsonl python3 run_claude.py $S 2 direct,none,card+resolver,explicit+card+resolver 4
  step B_inj $A python3 run_ablation.py $S $S "$INJ" --amb --step 2 --workers 4
  step B_fact $A python3 run_ablation.py $S $S "$FACT" --amb --step 2 --workers 4
  step B_same $A python3 run_ablation.py $S $S "$SAMEA" --amb --same --step 2 --workers 4
fi
if want C; then
  step C_fact_haiku $A python3 run_ablation.py $H $H "$FACT" --amb --step 2 --workers 4
  step C_same_opus $A python3 run_ablation.py $O $O "$SAMEA" --amb --same --step 2 --workers 4
  step C_cross_OH $A python3 run_ablation.py $O $H "none,explicit+card+resolver,explicit+inferred+resolver" --amb --step 2 --workers 4
  step C_cross_HO $A python3 run_ablation.py $H $O "none,explicit+card+resolver,explicit+inferred+resolver" --amb --step 2 --workers 4
fi
if want D; then for m in $O $S $H; do step D_probe_$m $P python3 run_probe.py $m "neutral,sender,sender+explicit" --workers 4; done; fi
if want F; then
  step F_fable $E python3 run_e2e.py $F $F "$MAIN4" --split heldout --step 2 --workers 3
  step F_gpt $E python3 run_e2e.py $G $G "none,explicit+inferred+resolver,ground+xcheck+readback" --split heldout --step 4 --workers 2
fi
if want G; then for m in $O $S $H; do step G_rep1_$m $E python3 run_e2e.py $m $m "$MAIN4" --split heldout --rep 1 --workers 4; done; fi
log "pipeline complete"
