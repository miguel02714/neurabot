from flask import Flask, request, render_template, jsonify, redirect, url_for, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import difflib
import unicodedata
import string
from models import Usuario, Mensagem, QA, db
from faq import qa_dict
import cohere
import os

app = Flask(__name__)
app.secret_key = 'lancode_secreta_12345'  # Chave secreta fixa
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

lm = LoginManager(app)
lm.login_view = 'login_view'

@lm.user_loader
def user_loader(id):
    return Usuario.query.get(int(id))

def normalizar(texto):
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = texto.translate(str.maketrans('', '', string.punctuation + ' '))
    return texto.lower()

def buscar_resposta(perguntas, mensagem):
    mensagem_norm = normalizar(mensagem)

    for item in perguntas:
        pergunta, resposta = item.split(":", 1)
        pergunta_norm = normalizar(pergunta)
        if pergunta_norm in mensagem_norm or mensagem_norm in pergunta_norm:
            return resposta.strip()

    perguntas_norm = [normalizar(p.split(":")[0]) for p in perguntas]
    correspondencias = difflib.get_close_matches(mensagem_norm, perguntas_norm, n=1, cutoff=0.6)

    if correspondencias:
        pergunta_original = next(p for p in perguntas if normalizar(p.split(":")[0]) == correspondencias[0])
        return pergunta_original.split(":")[1].strip()

    return None

# Cole sua chave da Cohere aqui:
COHERE_API_KEY = "VnAKRl6kF5ksOAEvhQWwuDI5XMwyWEVIdpEX6Krl"
co = cohere.Client(COHERE_API_KEY)

def buscar_resposta_gerada(mensagem):
    try:
        response = co.chat(model='command-r-plus', message=mensagem, max_tokens=150, temperature=0.7)
        return response.text.strip()
    except Exception as e:
        return f"Erro ao tentar se comunicar com a IA externa: {str(e)}"

def responder(mensagem):
    tema_atual = session.get('tema_atual')

    if tema_atual and tema_atual in qa_dict:
        resposta = buscar_resposta(qa_dict[tema_atual], mensagem)
        if resposta:
            return resposta

    resposta_gerada = buscar_resposta_gerada(mensagem)

    if not QA.query.filter_by(pergunta=mensagem).first():
        nova_qa = QA(pergunta=mensagem, resposta=resposta_gerada)
        db.session.add(nova_qa)
        db.session.commit()

    return resposta_gerada

@app.route('/')
def inicio():
    return render_template('inicio.html')

@app.route('/login', methods=["GET", "POST"])
def login_view():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        user = Usuario.query.filter_by(email=email).first()
        if user and check_password_hash(user.senha, senha):
            login_user(user)
            session.pop('tema_atual', None)
            return redirect(url_for("chat"))

        return render_template("login.html", erro="Email ou senha incorretos.")

    return render_template("login.html")

@app.route('/registrar', methods=["GET", "POST"])
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

@app.route('/logout', methods=["POST"])
@login_required
def logout():
    logout_user()
    session.pop('tema_atual', None)
    return redirect(url_for("login_view"))

@app.route('/chat', methods=["GET", "POST"])
@login_required
def chat():
    if request.method == "POST":
        data = request.get_json()
        mensagem = data.get("message", "")
        resposta = responder(mensagem)

        nova_mensagem = Mensagem(conteudo=mensagem, usuario_id=current_user.id)
        db.session.add(nova_mensagem)
        db.session.commit()

        return jsonify({"response": resposta})

    return render_template("chat.html",
                           nome_usuario=current_user.nome,
                           email_usuario=current_user.email)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")