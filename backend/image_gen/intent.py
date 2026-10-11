import re

# Palavras que indicam explicitamente vetor, código ou diagrama.
# A lista negativa tem precedência absoluta sobre verbos de desenho/criação.
VECTOR_NEGATIVE_KEYWORDS = {
    "svg",
    "vetor",
    "vetorial",
    "vector",
    "diagrama",
    "diagram",
    "fluxograma",
    "flowchart",
    "mermaid",
    "gráfico",
    "grafico",
    "chart",
    "ícone",
    "icone",
    "icon",
    "html",
    "código",
    "codigo",
    "code",
    "component",
    "componente",
}

SLASH_PREFIXES = ("/imagem", "/img", "/image")

# Verbos de desenho / pintura direta que por si só implicam imagem raster se não for vetor
DRAW_VERBS_REGEX = re.compile(
    r"\b(desenhe|desenha|desenhar|ilustre|ilustra|ilustrar|pinte|pinta|pintar|draw|paint)\b",
    re.IGNORECASE,
)

# Verbos de criação genérica combinados com substantivo de imagem
CREATE_VERBS_REGEX = re.compile(
    r"\b(gere|gera|gerar|crie|cria|criar|faça|faca|fazer|make|generate|create|render)\b",
    re.IGNORECASE,
)

IMAGE_NOUNS_REGEX = re.compile(
    r"\b(imagem|imagens|foto|fotos|fotografia|ilustra[çc][ãa]o|ilustra[çc][õo]es|figura|figuras|pintura|pinturas|retrato|retratos|desenho|desenhos|picture|pictures|image|images|photo|photos|wallpaper|painting|portrait)\b",
    re.IGNORECASE,
)


def classify_image_intent(text: str) -> str:
    """
    Classifica a intenção de geração de imagem.
    Retorna:
      - 'vector': pedido de SVG, diagrama, fluxograma, ícone ou código
      - 'raster': pedido de imagem de pixel (FLUX)
      - 'none': conversa de texto comum
    """
    if not text:
        return "none"

    raw = text.strip()
    lowered = raw.lower()

    # 1. Lista negativa: qualquer menção a vetor/diagrama/código vence o verbo
    tokens = set(re.findall(r"\w+", lowered))
    if any(k in tokens or k in lowered for k in VECTOR_NEGATIVE_KEYWORDS):
        return "vector"

    # 2. Comando slash explícito (/imagem, /img, /image)
    if any(lowered.startswith(prefix) for prefix in SLASH_PREFIXES):
        return "raster"

    # 3. Verbo direto de desenho/pintura ("desenhe um gato", "ilustre um farol")
    if DRAW_VERBS_REGEX.search(lowered):
        return "raster"

    # 4. Verbo de criação + substantivo de imagem ("crie uma imagem...", "gera uma foto...")
    if CREATE_VERBS_REGEX.search(lowered) and IMAGE_NOUNS_REGEX.search(lowered):
        return "raster"

    return "none"
