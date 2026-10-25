import yaml
import os

def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_config(config, path="config.yaml"):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)

def add_llm_profile(name, base_url, api_key, model_name, is_local):
    config = load_config()
    if "llm_profiles" not in config:
        config["llm_profiles"] = {}

    config["llm_profiles"][name] = {
        "type": "openai_compat",
        "base_url": base_url,
        "api_key": api_key,
        "model_name": model_name,
        "is_local": is_local
    }
    save_config(config)
