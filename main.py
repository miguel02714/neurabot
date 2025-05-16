from flask import Flask, request, render_template, jsonify, redirect, url_for, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import difflib
import unicodedata
import string
import requests
import json
from models import Usuario, Mensagem, QA
from db import db

import os
from dotenv import load_dotenv
load_dotenv()

# FAQ por tema
from faq import (
    apresentacao, funcionalidade, encerramento,
    curiosidades_gerais, ciencia_e_historia, geografia_e_linguas,
    literatura_e_arte, esportes, tecnologia_e_redes_sociais
)

app = Flask(__name__)
app.secret_key = 'lancode'
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.db"
db.init_app(app)

with app.app_context():
    db.create_all()

# Flask-Login
lm = LoginManager(app)
lm.login_view = 'login_view'

@lm.user_loader
def user_loader(id):
    return Usuario.query.get(int(id))

# Dicionário de FAQ por tema
qa_dict = {
    "apresentacao": apresentacao,
    "funcionalidade": funcionalidade,
    "encerramento": encerramento,
    "curiosidades_gerais": curiosidades_gerais,
    "ciencia_e_historia": ciencia_e_historia,
    "geografia_e_linguas": geografia_e_linguas,
    "literatura_e_arte": literatura_e_arte,
    "esportes": esportes,
    "tecnologia_e_redes_sociais": tecnologia_e_redes_sociais
}

# Normalização de texto
def normalizar(texto):
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto)
                    if unicodedata.category(c) != 'Mn')
    texto = texto.translate(str.maketrans('', '', string.punctuation + ' '))
    return texto.lower()

# Busca em FAQ
def buscar_resposta(perguntas, mensagem):
    mensagem_norm = normalizar(mensagem)

    # Busca exata
    for item in perguntas:
        pergunta, resposta = item.split(":", 1)
        pergunta_norm = normalizar(pergunta)
        if pergunta_norm in mensagem_norm or mensagem_norm in pergunta_norm:
            return resposta.strip()

    # Busca fuzzy
    perguntas_norm = [normalizar(p.split(":")[0]) for p in perguntas]
    correspondencias = difflib.get_close_matches(mensagem_norm, perguntas_norm, n=1, cutoff=0.6)

    if correspondencias:
        pergunta_original = next(p for p in perguntas if normalizar(p.split(":")[0]) == correspondencias[0])
        return pergunta_original.split(":")[1].strip()

    return None

# Fallback com IA externa (OpenRouter)

def buscar_resposta_gerada(mensagem):
    url = "https://openrouter.ai/api/v1/chat/completions"
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        print("❌ ERRO: OPENROUTER_API_KEY não está configurada.")
        return "Erro: chave de API não configurada no servidor. Por favor, contate o administrador."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": "MeuAppAI"
    }
    

    data = {
        "model": "qwen/qwen3-4b:free",
        "messages": [{"role": "user", "content": mensagem}]
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        resposta = response.json()

        if response.status_code == 200:
            if 'choices' in resposta and resposta['choices']:
                return resposta['choices'][0]['message']['content']
            else:
                return "Erro: Resposta inesperada da IA."
        else:
            return f"Erro: {resposta.get('error', {}).get('message', 'Desconhecido')}"

    except Exception as e:
        return f"Erro ao tentar se comunicar com a IA externa: {str(e)}"

# Função principal de resposta
def responder(mensagem):
    tema_atual = session.get('tema_atual')

    # 1. FAQ
    if tema_atual and tema_atual in qa_dict:
        resposta = buscar_resposta(qa_dict[tema_atual], mensagem)
        if resposta:
            return resposta

    # 2. Banco QA
    qa = QA.query.all()
    perguntas_banco = [f"{item.pergunta}:{item.resposta}" for item in qa]
    resposta = buscar_resposta(perguntas_banco, mensagem)
    if resposta:
        return resposta

    # 3. Fallback IA
    resposta_gerada = buscar_resposta_gerada(mensagem)

    # Salva no banco
    nova_qa = QA(pergunta=mensagem, resposta=resposta_gerada)
    db.session.add(nova_qa)
    db.session.commit()

    return resposta_gerada

# Rotas
@app.route('/')
def inicio():
    return render_template('inicio.html')

@app.route('/notfund')
def notfund():
    return render_template('404.html')

@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for('notfund'))

@app.route("/login", methods=["GET", "POST"])
def login_view():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        if not email or not senha:
            return render_template("login.html", erro="Preencha todos os campos.")

        user = Usuario.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.senha, senha):
            return render_template("login.html", erro="Email ou senha incorretos.")

        login_user(user)
        session.pop('tema_atual', None)
        return redirect(url_for("chat"))

    return render_template("login.html")

@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if request.method == "POST":
        nome = request.form.get("nome")
        email = request.form.get("email")
        senha = request.form.get("senha")

        if not nome or not email or not senha:
            return render_template("registrar.html", erro="Todos os campos são obrigatórios.")

        if Usuario.query.filter_by(email=email).first():
            return render_template("registrar.html", erro="Email já cadastrado.")

        senha_hash = generate_password_hash(senha)
        novo_usuario = Usuario(nome=nome, email=email, senha=senha_hash)
        db.session.add(novo_usuario)
        db.session.commit()

        login_user(novo_usuario)
        session.pop('tema_atual', None)
        return redirect(url_for("chat"))

    return render_template("registrar.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.pop('tema_atual', None)
    return redirect(url_for("login_view"))

@app.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    if request.method == "POST":
        data = request.get_json()
        user_input = data.get("message", "")
        response = responder(user_input)

        nova_mensagem = Mensagem(conteudo=user_input, usuario_id=current_user.id)
        db.session.add(nova_mensagem)
        db.session.commit()

        return jsonify({"response": response})

    return render_template("chat.html",
                           nome_usuario=current_user.nome,
                           email_usuario=current_user.email,
                           localizacao_usuario=getattr(current_user, "localizacao", "Não definida"))

@app.route('/perfil')
@login_required
def perfil():
    return render_template('perfil.html',
                           nome_usuario=current_user.nome,
                           email_usuario=current_user.email,
                           localizacao_usuario=getattr(current_user, "localizacao", "Não definida"))

@app.route('/ir-perfil', methods=["GET", "POST"])
def perfilGo():
    return redirect(url_for('perfil'))

@app.route('/voltar', methods=["GET", "POST"])
def voltarPerfil():
    return redirect(url_for('chat'))

@app.route("/mensagens")
@login_required
def mensagens():
    mensagens = Mensagem.query.order_by(Mensagem.id.desc()).limit(10).all()
    return jsonify([{
        "conteudo": m.conteudo,
        "usuario_id": m.usuario_id,
        "nome_usuario": m.usuario.nome
    } for m in mensagens])

# Execução
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0")
