# Cloud Run: la misma app de Streamlit, con 1 CPU real en vez del contenedor mínimo
# de Streamlit Cloud (que no aguanta la carga de LangChain al abrir el chat).
FROM python:3.13-slim
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app
COPY --chown=user app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir --user -r app/requirements.txt
ENV PATH="/home/user/.local/bin:$PATH"
COPY --chown=user . .
EXPOSE 7860
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true"]
