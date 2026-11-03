from streamlit.testing.v1 import AppTest

APP = "../app/streamlit_app.py"


def test_chat_cerrado_sin_codigo():
    at = AppTest.from_file(APP, default_timeout=60)
    at.secrets["CHAT_CODIGO"] = ""  # pisa el .streamlit/secrets.toml local, si existe
    at.run()
    assert not at.exception
    assert any("CHAT_CODIGO" in i.value for i in at.info)


def test_codigo_incorrecto_no_entra():
    at = AppTest.from_file(APP, default_timeout=60)
    at.secrets["CHAT_CODIGO"] = "secreto"
    at.run()
    at.text_input[0].input("otro").run()
    assert any("incorrecto" in e.value for e in at.error)
    assert not at.chat_input


def test_codigo_correcto_abre_el_chat():
    at = AppTest.from_file(APP, default_timeout=60)
    at.secrets["CHAT_CODIGO"] = "secreto"
    at.run()
    at.text_input[0].input("secreto").run()
    assert not at.exception
    assert at.chat_input
