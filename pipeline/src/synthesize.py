"""Synthesize step (LLM). One call per cluster: Italian summary.

Technical terms stay in English; source links are preserved. Output is validated against
the Synthesis schema (non-empty summary + at least one http source link). Same bounded
retry-then-skip and cost-cap discipline as classify. See docs/v1-architecture.md (§4.5).
"""

from __future__ import annotations

import sqlite3

from pydantic import ValidationError

from .llm import CostTracker, ItemProcessingError, LLMClient, extract_json
from .models import Synthesis

_SYSTEM = (
    "Sei un giornalista che scrive notizie originali in italiano, mantenendo i termini "
    "tecnici in inglese. Scrivi la notizia in terza persona riportando i fatti "
    "direttamente, come farebbe una testata. Rispondi SOLO con un oggetto JSON."
)


def _messages(members: list[sqlite3.Row]) -> list[dict]:
    stories = "\n".join(
        f"- {m['title']}: {(m['text'] or '')[:800]} ({m['link']})" for m in members
    )
    links = [m["link"] for m in members if m["link"]]
    user = (
        "Scrivi in italiano (termini tecnici in inglese) una scheda per questa notizia.\n\n"
        "REGOLA FONDAMENTALE: la descrizione DEVE essere la notizia stessa, scritta "
        "direttamente. NON riferirti alla fonte o a un articolo. È VIETATO usare parole o "
        "frasi come: 'l'articolo', 'il pezzo', 'la notizia', 'il report', 'il testo', "
        "'l'autore', 'la fonte', 'secondo', 'esplora', 'evidenzia', 'sottolinea', "
        "'descrive', 'spiega', 'analizza', 'illustra', 'riporta che', 'viene detto'.\n"
        "Esempio SBAGLIATO: \"L'articolo evidenzia come le aziende adottino l'AI.\"\n"
        'Esempio GIUSTO: "Le aziende stanno adottando l\'AI su larga scala."\n'
        "Vai dritto al punto, riporta i fatti.\n\n"
        "STRUTTURA A STRATI (come un giornale):\n"
        "Ogni campo deve aggiungere informazioni NUOVE e contestualizzate rispetto al "
        "precedente. Non ripetere mai ciò che è già stato detto in un campo precedente. "
        "Il lettore deve poter leggere in sequenza e scoprire sempre qualcosa di nuovo.\n\n"
        "1. title: il fatto principale in una frase incisiva. Solo l'essenziale.\n"
        "2. subtitle: aggiunge contesto non presente nel titolo (chi, quando, dove, "
        "perché, come). Una riga che completa il quadro.\n"
        "3. summary_it: 2-3 frasi che approfondiscono con fatti e dettagli nuovi, "
        "contestualizzati al titolo e sottotitolo. NON parafrasare il titolo.\n"
        "4. summary_long: 4-6 frasi che sviluppano la notizia in modo completo, "
        "aggiungendo numeri, dichiarazioni, implicazioni, retroscena. NON ripetere "
        "summary_it: espanderlo con più profondità.\n\n"
        "Esempio di gerarchia corretta:\n"
        '  title: "Apple presenta il chip M5"\n'
        '  subtitle: "Il nuovo processore promette un balzo del 40% nelle prestazioni '
        'AI on-device e arriverà sui Mac entro fine anno"\n'
        '  summary_it: "Il chip M5 è il primo processore Apple costruito con '
        'architettura a 3 nanometri di seconda generazione. Integra un Neural Engine '
        'da 32 core, capace di eseguire modelli linguistici fino a 20 miliardi di '
        'parametri interamente in locale, senza connessione internet."\n'
        '  summary_long: "Apple ha svelato il chip M5 durante un evento stampa a '
        'Cupertino. Il nuovo System-on-Chip rappresenta un salto generazionale '
        'rispetto al precedente M4, con un incremento del 40% nelle operazioni di '
        'machine learning e un\'efficienza energetica migliorata del 25%. '
        'Il Neural Engine a 32 core permette di eseguire modelli come Llama 3 e '
        'Mistral direttamente su dispositivo, senza latenza di rete e con maggiore '
        'privacy. I primi dispositivi con M5 saranno il MacBook Pro e l\'iMac, '
        'previsti per novembre 2025, con un prezzo di partenza invariato rispetto '
        'alla generazione precedente."\n\n'
        "Conserva i link alle fonti. Restituisci JSON con esattamente questi campi:\n"
        '{"title": "titolo breve e incisivo", '
        '"subtitle": "sottotitolo di una riga che aggiunge contesto nuovo", '
        '"summary_it": "la notizia in breve, 2-3 frasi con fatti nuovi, '
        'contestualizzati al titolo", '
        '"summary_long": "la notizia estesa, 4-6 frasi che approfondiscono '
        'con più dettagli, senza ripetere summary_it", '
        '"entities": ["nomi propri citati: aziende, prodotti, persone"], '
        '"source_links": ["https://..."]}\n'
        f"Link delle fonti da conservare: {links}\n\n"
        f"Elementi della notizia:\n{stories}"
    )
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def synthesize_cluster(
    llm: LLMClient,
    tracker: CostTracker,
    model: str,
    members: list[sqlite3.Row],
    max_validation_retries: int = 2,
) -> Synthesis:
    messages = _messages(members)
    last_err: Exception = ItemProcessingError("no attempt made")
    for _ in range(max_validation_retries + 1):
        tracker.check()  # raises CostCapExceeded -> stops the run
        res = llm.complete(model, messages)
        tracker.add(res.cost)
        try:
            return Synthesis.model_validate_json(extract_json(res.content))
        except ValidationError as exc:
            last_err = exc
            continue
    raise ItemProcessingError(f"invalid synthesis after retries: {last_err}")
