"""b-api (Bildungs-API) -- the LLM gateway of OpenEduHub.

    from edusharing.bapi import BildungsAPI

    async with BildungsAPI.from_env() as llm:
        print(await llm.chat("Summarise: ..."))

Without a fixed model id the least loaded ready text model is chosen. The
quirks of the model families -- which body layout, where thinking must be
switched off, where the very same flag is rejected with 400 -- live in
``body``, the choice in ``models``, and both are measured against the API
there.

The gateway forwards more than chat. ``embeddings``, ``moderate`` and ``images``
have methods of their own; ``call`` reaches other JSON routes such as
``responses`` and ``batches``, ``call_bytes`` reads binary responses such as
``audio/speech``, and ``call_multipart`` sends a file where a route wants one,
such as ``audio/transcriptions``. Which routes are forwarded at all was measured,
not read: see ``passthrough``, whose docstring also says why ``/v3/api-docs``
cannot answer that question.

    vectors = await llm.embeddings(["a", "b"], model="text-embedding-3-small",
                                   provider="openai")

That is the gateway's proxy mode: the caller sends the prompt. The same
gateway also keeps prompts on the server, in the metadata set -- the template
mode, ``BapiTemplates`` in ``templates``. It needs no ``BildungsAPI`` and
changes nothing about it; same key, same address:

    async with BapiTemplates.from_env() as templates:   # + EDU_SHARING_METADATASET
        text = await templates.chat(
            ["topic_page_ai_default", "topic_page_ai_chat_completion",
             "topic_page_ai_text_widget"], context_node_id=collection_id)
"""

from .body import build_body, read_answer
from .client import CACHE_FOREVER, BildungsAPI
from .models import (
    LoadReport,
    Model,
    load_report,
    pick_model,
    rank_among,
    rank_models,
)
from .passthrough import Answer, GeneratedImage, Moderation
from .templates import BapiTemplates, NodeConfig

__all__ = ["BildungsAPI", "BapiTemplates", "NodeConfig", "Model", "pick_model", "rank_models",
           "build_body", "read_answer",
           # Model choice and load
           "LoadReport", "load_report", "rank_among", "CACHE_FOREVER",
           # The forwarded OpenAI routes
           "Moderation", "GeneratedImage", "Answer"]
