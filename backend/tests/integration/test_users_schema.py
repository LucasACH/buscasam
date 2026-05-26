from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def test_users_row_round_trip_with_full_shape(session):
    await session.execute(
        text(
            "INSERT INTO users (google_sub, email, hd, role, name, picture_url) "
            "VALUES ('sub-1', 'ada@unsam.edu.ar', 'unsam.edu.ar', 'docente', "
            "'Ada Lovelace', 'https://example.test/a.png')"
        )
    )
    await session.commit()

    row = (
        await session.execute(
            text(
                "SELECT google_sub, email, hd, role, name, picture_url, "
                "created_at IS NOT NULL AS has_created, "
                "last_login_at IS NOT NULL AS has_last_login "
                "FROM users WHERE google_sub = 'sub-1'"
            )
        )
    ).mappings().one()

    assert row["google_sub"] == "sub-1"
    assert row["email"] == "ada@unsam.edu.ar"
    assert row["hd"] == "unsam.edu.ar"
    assert row["role"] == "docente"
    assert row["name"] == "Ada Lovelace"
    assert row["picture_url"] == "https://example.test/a.png"
    assert row["has_created"] is True
    assert row["has_last_login"] is True


async def test_users_google_sub_is_unique(session):
    await session.execute(
        text(
            "INSERT INTO users (google_sub, email, hd, role, name) "
            "VALUES ('dup-sub', 'a@unsam.edu.ar', 'unsam.edu.ar', 'docente', 'A')"
        )
    )
    await session.commit()

    try:
        await session.execute(
            text(
                "INSERT INTO users (google_sub, email, hd, role, name) "
                "VALUES ('dup-sub', 'b@unsam.edu.ar', 'unsam.edu.ar', "
                "'docente', 'B')"
            )
        )
        await session.commit()
    except IntegrityError:
        pass
    else:
        raise AssertionError("expected unique violation on google_sub")
