from flask import Flask, request, render_template, jsonify, redirect, url_for, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import difflib
import unicodedata
import string

from models import Usuario, Mensagem
from db import db
from faq import (
    apresentacao, funcionalidade, encerramento,
    curiosidades_gerais, ciencia_e_historia, geografia_e_linguas,
    literatura_e_arte, esportes, tecnologia_e_redes_sociais
)

app = Flask(__name__)
app.secret_key = 'lancode'
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.db"
db.init_app(app)

# Login manager
lm = LoginManager(app)
lm.login_view = 'login'

@lm.user_loader
def user_loader(id):
    return db.session.query(Usuario).filter_by(id=id).first()

# Dicionário de QA para cada categoria
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

def normalizar(texto):
    texto = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    texto = texto.translate(str.maketrans('', '', string.punctuation + ' '))
    return texto.lower()

def responder(mensagem):
    mensagem_norm = normalizar(mensagem)
    tema_atual = session.get('tema_atual', None)

    def buscar_resposta(perguntas):
        for item in perguntas:
            pergunta, resposta = item.split(":", 1)
            pergunta_norm = normalizar(pergunta)
            if pergunta_norm in mensagem_norm or mensagem_norm in pergunta_norm:
                return resposta
        perguntas_norm = [normalizar(p.split(":")[0]) for p in perguntas]
        correspondencias = difflib.get_close_matches(mensagem_norm, perguntas_norm, n=1, cutoff=1.0)
        if correspondencias:
            pergunta_original = next(p for p in perguntas if normalizar(p.split(":")[0]) == correspondencias[0])
            return pergunta_original.split(":")[1].strip()
        return None

    # 1. Tenta com tema atual
    if tema_atual:
        resposta = buscar_resposta(qa_dict[tema_atual])
        if resposta:
            return f"Olá {resposta}"

    # 2. Procura em outros temas
    for tema, perguntas in qa_dict.items():
        resposta = buscar_resposta(perguntas)
        if resposta:
            session['tema_atual'] = tema
            return resposta

    # 3. Nenhuma resposta encontrada
    return "Desculpe, não entendi isso. Pode reformular?"

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

    # Método GET: carrega a interface
    return render_template("index.html",
        nome_usuario=current_user.nome,
        email_usuario=current_user.email,
        localizacao_usuario=getattr(current_user, "localizacao", "Não definida"))

@app.route("/mensagens")
@login_required
def mensagens():
    mensagens = Mensagem.query.order_by(Mensagem.id.desc()).limit(10).all()
    return jsonify([
        {
            "conteudo": m.conteudo,
            "usuario_id": m.usuario_id,
            "nome_usuario": m.usuario.nome
        } for m in mensagens
    ])

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        if not email or not senha:
            return render_template("login.html", erro="Por favor, preencha ambos os campos.")

        user = Usuario.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.senha, senha):
            return render_template("login.html", erro="Usuário ou senha incorretos.")

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

        # Verifica se todos os campos foram preenchidos
        if not nome or not email or not senha:
            return render_template("registrar.html", erro="Todos os campos são obrigatórios.")

        # Verifica se o email já está cadastrado
        if Usuario.query.filter_by(email=email).first():
            return render_template("registrar.html", erro="Email já cadastrado.")

        # Cria novo usuário
        senha_hash = generate_password_hash(senha)
        novo_usuario = Usuario(nome=nome, email=email, senha=senha_hash)
        db.session.add(novo_usuario)
        db.session.commit()

        # Faz login automático
        login_user(novo_usuario)
        session.pop('tema_atual', None)

        return redirect(url_for("chat"))

    # Se for GET, mostra o formulário de registro
    return render_template("registrar.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.pop('tema_atual', None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0")
