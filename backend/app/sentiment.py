from functools import lru_cache


MODEL_ID = "monologg/koelectra-small-finetuned-nsmc"


@lru_cache(maxsize=1)
def _load_model():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID)
    model.eval()
    # Dynamic INT8 quantization reduces resident CPU memory for linear layers.
    # Evaluation runs on CPU, so no GPU specific quantization path is required.
    model = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
    return tokenizer, model


def analyze_sentiment(text: str) -> dict[str, str | float]:
    tokenizer, model = _load_model()
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
    with torch.inference_mode():
        logits = model(**inputs).logits[0]
        probabilities = torch.softmax(logits, dim=-1)

    positive_index = int(model.config.label2id.get("positive", 1))
    negative_index = int(model.config.label2id.get("negative", 0))
    positive_probability = float(probabilities[positive_index])
    negative_probability = float(probabilities[negative_index])
    score = positive_probability - negative_probability
    label = "긍정" if score >= 0 else "부정"
    confidence = max(positive_probability, negative_probability)
    return {
        "label": label,
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "model": MODEL_ID,
    }
