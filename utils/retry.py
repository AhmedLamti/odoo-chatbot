"""
Décorateur retry réutilisable — Phase 5
Appliqué sur tous les appels externes : Cerebras, Groq, PostgreSQL, XML-RPC Odoo
"""

import time
import logging
import functools
from typing import Callable, Type

logger = logging.getLogger(__name__)


def with_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """
    Décorateur retry avec backoff exponentiel.

    Paramètres :
        max_attempts : nombre max de tentatives (défaut: 3)
        delay        : délai initial en secondes entre tentatives (défaut: 1.0)
        backoff      : multiplicateur du délai à chaque tentative (défaut: 2.0)
        exceptions   : tuple des exceptions à capturer (défaut: toutes)

    Exemple :
        @with_retry(max_attempts=3, delay=1.0, backoff=2.0)
        def call_cerebras(...): ...
        # Tentative 1 → échec → attendre 1s
        # Tentative 2 → échec → attendre 2s
        # Tentative 3 → échec → raise exception
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"[{func.__name__}] Tentative {attempt}/{max_attempts} échouée: {e} "
                            f"— retry dans {current_delay:.1f}s"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"[{func.__name__}] Toutes les tentatives épuisées ({max_attempts}/{max_attempts}): {e}"
                        )

            raise last_exception

        return wrapper

    return decorator
