import pytest
from pydantic import ValidationError

from app.crud import player as player_crud
from app.models import Player
from tests.utils.utils import random_steamid64


def test_normalize_custom_id_lowercases_valid_ids() -> None:
    assert player_crud.normalize_custom_id("  Mixed_Name-42 ") == "mixed_name-42"


@pytest.mark.parametrize("custom_id", ["123456", "bad.id", "bad!id"])
def test_normalize_custom_id_discards_invalid_ids(custom_id: str) -> None:
    assert player_crud.normalize_custom_id(custom_id) is None


def test_player_model_normalizes_custom_id_on_create() -> None:
    player = Player(
        steamid64=random_steamid64(),
        name="Runner",
        custom_id="  Mixed_Name-42 ",
    )

    assert player.custom_id == "mixed_name-42"


@pytest.mark.parametrize("custom_id", ["123456", "bad.id", "bad!id"])
def test_player_model_rejects_invalid_custom_id_on_create(custom_id: str) -> None:
    with pytest.raises(ValidationError):
        Player(
            steamid64=random_steamid64(),
            name="Runner",
            custom_id=custom_id,
        )


def test_player_model_rejects_invalid_custom_id_assignment() -> None:
    player = Player(steamid64=random_steamid64(), name="Runner")

    with pytest.raises(ValidationError):
        player.custom_id = "123456"
