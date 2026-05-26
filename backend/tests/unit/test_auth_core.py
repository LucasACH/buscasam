"""Unit tests for `core/auth` per ADR-0005 §3 and module map §`core/auth`."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from buscasam.core import auth


def test_hd_to_role_mapping():
    assert auth.ROLE_BY_HD == {
        "estudiantes.unsam.edu.ar": "estudiante",
        "unsam.edu.ar": "docente",
    }

    with pytest.raises(KeyError):
        auth.ROLE_BY_HD["evil.com"]


@pytest.mark.parametrize(
    "raw",
    ["/buscar?q=tesis", "/", "/buscar", "/docs/42#fragment"],
)
def test_next_validation_accepts_relative_paths(raw):
    assert auth.safe_next(raw) == raw


@pytest.mark.parametrize(
    "raw",
    ["//evil.com", "https://evil.com", "buscar", "", None, "javascript:alert(1)"],
)
def test_next_validation_rejects_unsafe(raw):
    assert auth.safe_next(raw) == "/"


@pytest.mark.parametrize(
    "claims",
    [
        {"email_verified": True, "sub": "x"},  # no hd
        {"email_verified": True, "sub": "x", "hd": "example.com"},  # wrong hd
        {  # right hd but unverified email
            "email_verified": False,
            "sub": "x",
            "hd": "unsam.edu.ar",
        },
    ],
)
def test_claim_acceptance_matrix_rejects(claims):
    assert auth.role_from_claims(claims) is None


def test_claim_acceptance_matrix_accepts_estudiante():
    role = auth.role_from_claims(
        {
            "email_verified": True,
            "sub": "google-sub-1",
            "hd": "estudiantes.unsam.edu.ar",
        }
    )
    assert role == "estudiante"


def test_claim_acceptance_matrix_accepts_docente():
    role = auth.role_from_claims(
        {
            "email_verified": True,
            "sub": "google-sub-2",
            "hd": "unsam.edu.ar",
        }
    )
    assert role == "docente"


async def test_jit_user_upsert(session):
    uid1 = await auth.upsert_user(
        session,
        google_sub="sub-jit",
        email="ada@unsam.edu.ar",
        hd="unsam.edu.ar",
        role="docente",
        name="Ada Lovelace",
        picture_url="https://example.test/a.png",
    )

    uid2 = await auth.upsert_user(
        session,
        google_sub="sub-jit",
        email="ada+new@unsam.edu.ar",
        hd="estudiantes.unsam.edu.ar",
        role="estudiante",
        name="Ada L.",
        picture_url=None,
    )

    assert uid1 == uid2

    count = (
        await session.execute(
            text("SELECT count(*) FROM users WHERE google_sub = 'sub-jit'")
        )
    ).scalar_one()
    assert count == 1

    row = (
        await session.execute(
            text(
                "SELECT email, hd, role, name, picture_url "
                "FROM users WHERE google_sub = 'sub-jit'"
            )
        )
    ).mappings().one()
    assert row == {
        "email": "ada+new@unsam.edu.ar",
        "hd": "estudiantes.unsam.edu.ar",
        "role": "estudiante",
        "name": "Ada L.",
        "picture_url": None,
    }
