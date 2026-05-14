#!/usr/bin/env python3
"""
Test script pour /api/chat/stream
Usage: python test_stream.py [question]
"""

import json
import sys
import requests

BACKEND_URL = "http://127.0.0.1:8000"
QUESTION = sys.argv[1] if len(sys.argv) > 1 else "Bonjour, qui es-tu ?"


def test_stream():
    print(f"\n{'='*60}")
    print(f"  TEST /api/chat/stream")
    print(f"  Question : {QUESTION}")
    print(f"{'='*60}\n")

    try:
        with requests.post(
            f"{BACKEND_URL}/api/chat/stream",
            json={"question": QUESTION, "session_id": "test-session-001"},
            stream=True,
            timeout=120,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            print(f"[HTTP] Status     : {resp.status_code}")
            print(f"[HTTP] Content-Type: {resp.headers.get('content-type', 'N/A')}")
            print(f"[HTTP] Transfer   : {resp.headers.get('transfer-encoding', 'N/A')}\n")

            if resp.status_code != 200:
                print(f"[ERREUR] Réponse inattendue :")
                print(resp.text)
                return

            step_count = 0
            final_received = False
            done_received = False

            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue

                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line

                if not line.startswith("data: "):
                    print(f"[WARN] Ligne inattendue : {line!r}")
                    continue

                payload = line[6:]

                if payload == "[DONE]":
                    done_received = True
                    print(f"\n[DONE] Stream terminé ✓")
                    break

                try:
                    item = json.loads(payload)
                    item_type = item.get("type", "unknown")

                    if item_type == "step":
                        step_count += 1
                        print(f"[STEP {item.get('step', '?')}] {item.get('message', '')}")

                    elif item_type == "final":
                        final_received = True
                        print(f"\n[FINAL]")
                        print(f"  route   : {item.get('route', 'N/A')}")
                        print(f"  sources : {item.get('sources', [])}")
                        print(f"  steps   : {item.get('steps', [])}")
                        answer = item.get("answer", "")
                        preview = answer[:200] + "…" if len(answer) > 200 else answer
                        print(f"  answer  : {preview}")

                    else:
                        print(f"[{item_type.upper()}] {payload}")

                except json.JSONDecodeError:
                    print(f"[WARN] JSON invalide : {payload!r}")

            print(f"\n{'='*60}")
            print(f"  RÉSUMÉ")
            print(f"  Steps reçus    : {step_count}")
            print(f"  Final reçu     : {'✓' if final_received else '✗ MANQUANT'}")
            print(f"  DONE reçu      : {'✓' if done_received else '✗ MANQUANT'}")

            if not final_received:
                print(f"\n  [ERREUR] Le event 'final' n'est jamais arrivé.")
                print(f"  → Vérifier que run_orchestrator() retourne bien un dict")
                print(f"    avec les clés : answer, route, steps, sources")

            if not done_received:
                print(f"\n  [ERREUR] Le sentinel None n'a pas été mis dans la queue.")
                print(f"  → Vérifier que run_agent() ne plante pas silencieusement")
                print(f"    (wrapper try/except manquant dans run_agent)")

            print(f"{'='*60}\n")

    except requests.exceptions.ConnectionError:
        print(f"[ERREUR] Impossible de joindre {BACKEND_URL}")
        print(f"  → Le serveur FastAPI est-il démarré ? (uvicorn main:app --reload)")
    except requests.exceptions.Timeout:
        print(f"[ERREUR] Timeout — l'agent ne répond pas dans les 120s")
    except Exception as e:
        print(f"[ERREUR] Exception inattendue : {type(e).__name__}: {e}")


def test_health():
    """Vérifie aussi que le serveur répond sur /api/chat (non-stream)"""
    print(f"\n[HEALTH CHECK] GET {BACKEND_URL}/docs")
    try:
        r = requests.get(f"{BACKEND_URL}/docs", timeout=5)
        print(f"  → {r.status_code} {'✓ serveur UP' if r.status_code == 200 else '?'}")
    except Exception as e:
        print(f"  → ERREUR : {e}")


if __name__ == "__main__":
    test_health()
    test_stream()
