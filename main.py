from flask import Flask, request, render_template, jsonify, redirect, url_for, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import difflib
import unicodedata
import string
import requests
from models import Usuario, Mensagem, QA
from db import db
import cohere
import os
from dotenv import load_dotenv
from google.auth.transport import requests as google_requests

load_dotenv()

# Importa FAQs por tema
from faq import (
    apresentacao
)

# Flask config
app = Flask(__name__)
app.secret_key = 'lancode'
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.db"
db.init_app(app)

with app.app_context():
    db.create_all()

# Login Manager
lm = LoginManager(app)
lm.login_view = 'login_view'

@lm.user_loader
def user_loader(id):
    return Usuario.query.get(int(id))

# FAQs por tema
qa_dict = {
    "apresentacao": apresentacao,
    }

# Função para normalizar texto
def normalizar(texto):
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = texto.translate(str.maketrans('', '', string.punctuation + ' '))
    return texto.lower()


@app.route('/auth/google', methods=['POST'])
def auth_google():
    try:
        token = request.json.get('token')
        if not token:
            return jsonify({"error": "Token não enviado"}), 400

        # Verifica o token recebido com a API do Google
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), audience="AIzaSyCWyL9ENPHqRtfSpKyrAtML7VigfQ9lS4g")

        # idinfo tem dados do usuário, como:
        user_id = idinfo['sub']
        email = idinfo.get('email')
        name = idinfo.get('name')

        # Aqui você faria: buscar o usuário no banco e criar se não existir
        if user_id not in users:
            users[user_id] = {
                'email': email,
                'name': name
            }
            created = True
        else:
            created = False

        # Retorna dados do usuário para o frontend
        return jsonify({
            "user_id": user_id,
            "email": email,
            "name": name,
            "created": created
        })

    except ValueError:
        # Token inválido
        return jsonify({"error": "Token inválido"}), 401




# Busca por resposta em FAQ
def buscar_resposta(perguntas, mensagem):
    mensagem_norm = normalizar(mensagem)
    for item in perguntas:
        pergunta, resposta = item.split(":", 1)
        if normalizar(pergunta) in mensagem_norm or mensagem_norm in normalizar(pergunta):
            return resposta.strip()
    perguntas_norm = [normalizar(p.split(":")[0]) for p in perguntas]
    correspondencias = difflib.get_close_matches(mensagem_norm, perguntas_norm, n=1, cutoff=0.6)
    if correspondencias:
        pergunta_original = next(p for p in perguntas if normalizar(p.split(":")[0]) == correspondencias[0])
        return pergunta_original.split(":")[1].strip()
    return None

# Cliente Cohere
co = cohere.Client(os.getenv("COHERE_API_KEY") or "VnAKRl6kF5ksOAEvhQWwuDI5XMwyWEVIdpEX6Krl")

def buscar_resposta_gerada(mensagem):
    try:
        response = co.chat(
            model='command-r-plus',
            message=mensagem,
            max_tokens=150,
            temperature=0.7
        )
        return response.text.strip()
    except Exception as e:
        return f"Erro ao tentar se comunicar com a IA externa: {str(e)}"

@app.route('/transcrever-audio', methods=['POST'])
@login_required
def transcrever_audio():
    if 'audio' not in request.files:
        return jsonify({'erro': 'Nenhum arquivo enviado'}), 400

    audio_file = request.files['audio']
    filename = secure_filename(audio_file.filename)
    audio_path = os.path.join('audios_temp', filename)
    os.makedirs('audios_temp', exist_ok=True)
    audio_file.save(audio_path)

    recognizer = sr.Recognizer()
    with sr.AudioFile(audio_path) as source:
        audio_data = recognizer.record(source)

    try:
        texto = recognizer.recognize_google(audio_data, language='pt-BR')
        return jsonify({'texto': texto})
    except sr.UnknownValueError:
        return jsonify({'erro': 'Não foi possível entender o áudio.'}), 400
    except sr.RequestError:
        return jsonify({'erro': 'Erro ao se conectar com o serviço de transcrição.'}), 500

# Lógica combinada de resposta
def responder(mensagem):
    # Comando para gerar imagem
    if mensagem.lower().startswith("gerar imagem:"):
        prompt = mensagem[len("gerar imagem:"):].strip()
        return gerar_imagem_freepik(prompt)  # Certifique-se de implementar essa função

    tema_atual = session.get('tema_atual')

    # 1. Busca em FAQ do tema atual (se estiver definido)
    if tema_atual and tema_atual in qa_dict:
        resposta = buscar_resposta(qa_dict[tema_atual], mensagem)
        if resposta:
            return resposta

    # 2. Busca em todos os temas disponíveis (não só "geral")
    for tema, perguntas in qa_dict.items():
        resposta = buscar_resposta(perguntas, mensagem)
        if resposta:
            return resposta

    # 3. Se não encontrou em nenhum FAQ, gera com IA
    resposta_gerada = buscar_resposta_gerada(mensagem)

    # 4. Salva no banco
    nova_qa = QA(pergunta=mensagem, resposta=resposta_gerada)
    db.session.add(nova_qa)
    db.session.commit()

    return resposta_gerada

# Rotas principais
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
        # Verifica se é JSON (como login via Google)
        if request.is_json:
            data = request.get_json()
            email = data.get("email")
            nome = data.get("nome")  # caso precise do nome também

            if not email:
                return jsonify({"status": "erro", "mensagem": "Email é obrigatório."}), 400

            user = Usuario.query.filter_by(email=email).first()

            if not user:
                # Usuário ainda não existe, cria com senha falsa (como você fez no /registrar)
                senha_fake = generate_password_hash("google_login")
                user = Usuario(nome=nome or "Usuário Google", email=email, senha=senha_fake)
                db.session.add(user)
                db.session.commit()

            login_user(user)
            session.pop("tema_atual", None)
            return jsonify({"status": "sucesso"})

        # Caso contrário: formulário tradicional
        email = request.form.get("email")
        senha = request.form.get("senha")

        if not email or not senha:
            return render_template("login.html", erro="Preencha todos os campos.")

        user = Usuario.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.senha, senha):
            return render_template("login.html", erro="Email ou senha incorretos.")

        login_user(user)
        session.pop("tema_atual", None)
        return redirect(url_for("chat"))

    return render_template("login.html")

@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json()
            nome = data.get("nome")
            email = data.get("email")
            if not nome or not email:
                return jsonify({"status": "erro", "mensagem": "Dados incompletos."})
            usuario_existente = Usuario.query.filter_by(email=email).first()
            if usuario_existente:
                login_user(usuario_existente)
                session.pop("tema_atual", None)
                return jsonify({"status": "sucesso"})
            senha_fake = generate_password_hash("google_login")
            novo_usuario = Usuario(nome=nome, email=email, senha=senha_fake)
            db.session.add(novo_usuario)
            db.session.commit()
            login_user(novo_usuario)
            session.pop("tema_atual", None)
            return jsonify({"status": "sucesso"})
        
        # Caso seja formulário tradicional
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
        session.pop("tema_atual", None)
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

@app.route("/chat1", methods=["GET", "POST"])
@login_required
def chat1():
    if request.method == "POST":
        data = request.get_json()
        user_input = data.get("message", "")
        response = responder(user_input)
        nova_mensagem = Mensagem(conteudo=user_input, usuario_id=current_user.id)
        db.session.add(nova_mensagem)
        db.session.commit()
        return jsonify({"response": response})
    return render_template("chat1.html",
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

@app.route('/registrar-conta', methods=["GET", "POST"])
def registrarconta():
    return redirect(url_for('registrar'))

@app.route('/ir-login', methods=["GET", "POST"])
def irlogin():
    return redirect(url_for('login_view'))

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
