"""Mede o consumo REAL de tokens por botao e variante de geracao.

Chama o Groq de verdade (consome cota da sua chave). Use para decidir configuracoes com
numero, por exemplo se reduzir o esforco de raciocinio economiza sem piorar a fidelidade.

    python scripts/measure_tokens.py --variants baseline,low --reps 2
    python scripts/measure_tokens.py --buttons sumario,flashcards --show

O abstract abaixo e SINTETICO (inventado para este teste); nao representa um estudo real.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "nexus-science"))

import prompt_builders as pb  # noqa: E402
from generation import GenerationOptions  # noqa: E402
from grounding import check_numeric_grounding  # noqa: E402
from llm_service import get_router  # noqa: E402
from workflow import wrap_source  # noqa: E402

TITLE = "Metformin and cardiovascular outcomes in older adults with type 2 diabetes: a multicenter cohort study"
ABSTRACT = (
    "Background: Metformin is widely used as first-line therapy in type 2 diabetes, but its effect on cardiovascular "
    "outcomes in older adults remains uncertain. Methods: We conducted a multicenter retrospective cohort study "
    "including 12,450 adults aged 60 years or older with newly diagnosed type 2 diabetes between 2015 and 2021. "
    "Patients were followed for a median of 4.2 years. The primary outcome was a composite of myocardial infarction, "
    "stroke, and cardiovascular death. Cox proportional hazards models adjusted for age, sex, body mass index, renal "
    "function, and baseline HbA1c were used. Results: Metformin use was associated with a lower risk of the primary "
    "outcome (HR 0.82; 95% CI 0.74-0.91; p<0.001). Benefits were consistent across subgroups, although attenuated in "
    "patients with eGFR below 45 mL/min. Gastrointestinal adverse events were more frequent in the metformin group "
    "(11.3% vs 6.1%). Conclusions: In older adults, metformin was associated with fewer cardiovascular events. "
    "Residual confounding cannot be excluded, and randomized trials are needed."
)

BUTTONS = {
    "sumario": pb.build_message_sumario,
    "estatisticas": pb.build_message_estatisticas,
    "critica_metodologica": pb.build_message_critica_metodologica,
    "flashcards": pb.build_message_flashcards,
}
VARIANTS = {
    "baseline": None,  # parametros padrao do provedor (como era antes da Fase 2)
    "t02": GenerationOptions(temperature=0.2),
    "low": GenerationOptions(temperature=0.2, reasoning_effort="low"),
    "medium": GenerationOptions(temperature=0.2, reasoning_effort="medium"),
    "low_cap": GenerationOptions(temperature=0.2, reasoning_effort="low", max_output_tokens=1500),
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # consoles Windows usam cp1252
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="GPT-OSS 20B (Groq)")
    parser.add_argument("--variants", default="baseline,low")
    parser.add_argument("--buttons", default=",".join(BUTTONS))
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--show", action="store_true", help="imprime as respostas")
    parser.add_argument("--out", help="grava os resultados brutos em JSON")
    args = parser.parse_args()

    router = get_router()
    router.ensure_available(args.model)
    rows = []
    for variant in args.variants.split(","):
        options = VARIANTS[variant]
        for button in args.buttons.split(","):
            builder = BUTTONS[button]
            for rep in range(args.reps):
                messages = builder(wrap_source("SOURCE_TITLE", TITLE), wrap_source("SOURCE_ABSTRACT", ABSTRACT))
                started = time.monotonic()
                completion = router.complete(messages, args.model, options)
                elapsed = time.monotonic() - started
                grounding = check_numeric_grounding(completion.text, f"{TITLE}\n{ABSTRACT}")
                rows.append({
                    "variant": variant, "button": button, "rep": rep,
                    "prompt": completion.prompt_tokens, "completion": completion.completion_tokens,
                    "total": completion.total_tokens, "seconds": round(elapsed, 1),
                    "chars": len(completion.text), "truncated": completion.truncated,
                    "ungrounded": grounding.ungrounded,
                    "not_described": completion.text.count("Não descrito no resumo fornecido"),
                })
                if args.show:
                    print(f"\n===== {variant} / {button} #{rep} =====\n{completion.text}\n")

    print(f"\nmodelo: {args.model} | repeticoes: {args.reps}\n")
    print(f"{'variante':<10} {'prompt':>7} {'saida':>7} {'total':>7} {'seg':>5} {'chars':>6} {'cortadas':>8} {'num.sem.fonte':>13}")
    for variant in args.variants.split(","):
        sel = [r for r in rows if r["variant"] == variant]

        def mean(key: str, sel: list = sel) -> float:
            return statistics.mean(r[key] for r in sel)

        print(f"{variant:<10} {mean('prompt'):>7.0f} {mean('completion'):>7.0f} {mean('total'):>7.0f} "
              f"{mean('seconds'):>5.1f} {mean('chars'):>6.0f} {sum(r['truncated'] for r in sel):>8} "
              f"{sum(len(r['ungrounded']) for r in sel):>13}")
    print("\npor botao (saida media):")
    for button in args.buttons.split(","):
        cells = []
        for variant in args.variants.split(","):
            sel = [r for r in rows if r["variant"] == variant and r["button"] == button]
            cells.append(f"{variant}={statistics.mean(r['completion'] for r in sel):.0f}")
        print(f"  {button:<22} " + "  ".join(cells))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
