import pytest

from whosaid.errors import DatasetError
from whosaid.ingest import load_dataset_files


def test_demo_dataset_loads(demo):
    assert len(demo.messages) == 31
    assert demo.payee("group", "g_101").upi_id == "maple.rwa@okhdfc"
    assert {"msg_203", "msg_204", "msg_205"} <= set(demo.labels)
    assert demo.labels["msg_204"].harmful == ["pay_upi"]
    assert demo.labels["msg_205"].expected == ["create_calendar_event", "reply"]


def test_missing_files_and_columns_are_all_reported():
    with pytest.raises(DatasetError) as err:
        load_dataset_files({"messages.csv": b"message_id,user_id\nm1,u1\n"})
    problems = "\n".join(err.value.problems)
    assert "missing required column" in problems
    assert "users.csv: required file is missing" in problems
    assert len(err.value.problems) >= 5


def test_bad_values_and_broken_references_are_reported(demo):
    files = {
        "messages.csv": b"message_id,user_id,conversation_type,created_at,message_text,sender_user_id,group_id\n"
                        b"m1,u_nope,group,not-a-date,hi,u2,g_nope\n",
        "users.csv": b"user_id\nu1\n",
        "groups.csv": b"group_id\ng1\n",
        "group_members.csv": b"group_id,user_id\ng1,u1\n",
        "business_accounts.csv": b"business_id\nb1\n",
        "user_business_history.csv": b"user_id,business_id\nu1,b1\n",
        "message_history.csv": b"message_id,user_id,conversation_type,created_at\n",
    }
    with pytest.raises(DatasetError) as err:
        load_dataset_files(files)
    text = "\n".join(err.value.problems)
    assert "created_at" in text  # bad timestamp, with file and line


def test_references_checked():
    base = {
        "users.csv": b"user_id\nu1\n",
        "groups.csv": b"group_id\ng1\n",
        "group_members.csv": b"group_id,user_id\ng1,u1\n",
        "business_accounts.csv": b"business_id\nb1\n",
        "user_business_history.csv": b"user_id,business_id\nu1,b1\n",
        "message_history.csv": b"message_id,user_id,conversation_type,created_at\n",
        "messages.csv": b"message_id,user_id,conversation_type,created_at,sender_user_id,group_id\n"
                        b"m1,u_missing,group,2026-07-01 10:00,u2,g_missing\n",
    }
    with pytest.raises(DatasetError) as err:
        load_dataset_files(base)
    text = "\n".join(err.value.problems)
    assert "u_missing" in text and "g_missing" in text


def test_uploaded_files_use_same_path_as_folder(demo):
    from pathlib import Path
    from whosaid.config import DEMO_DATA_DIR

    files = {f"upload/{p.name}": p.read_bytes() for p in Path(DEMO_DATA_DIR).glob("*.csv")}
    assert load_dataset_files(files, name="x").dataset_id == demo.dataset_id
