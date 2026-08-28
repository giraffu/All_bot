import json
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def test_observer_has_an_isolated_prod_image_and_env_projection():
    catalog = json.loads((ROOT / "deploy/module-catalog.json").read_text())
    compose = yaml.safe_load(
        (ROOT / "deploy/docker-compose-cloud-base.yml").read_text()
    )
    env_contract = json.loads((ROOT / "deploy/service-env-contract.yml").read_text())

    module = catalog["modules"]["observer-bot"]
    service = compose["services"]["observer-bot"]
    projection = env_contract["services"]["observer-bot"]

    assert module["environments"] == ["prod"]
    assert module["profile"] == "observer"
    assert service["profiles"] == ["observer"]
    assert "observer-bot.env" in service["env_file"][0]["path"]
    assert projection["patterns"] == ["OBSERVER_*", "TELEGRAM_*"]
    assert "DATABASE_URL" not in projection["required"]
    assert "OBSERVER_DATABASE_URL" in projection["required"]
