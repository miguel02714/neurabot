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
    try:
        if request.method == "POST":
            if request.is_json:
                data = request.get_json()
                if not data:
                    return jsonify({"status": "erro", "mensagem": "JSON inválido."}), 400
                
                email = data.get("email")
                nome = data.get("nome")  # opcional
                
                if not email:
                    return jsonify({"status": "erro", "mensagem": "Email é obrigatório."}), 400
                
                user = Usuario.query.filter_by(email=email).first()
                
                if not user:
                    senha_fake = generate_password_hash("google_login")
                    user = Usuario(nome=nome or "Usuário Google", email=email, senha=senha_fake)
                    db.session.add(user)
                    db.session.commit()
                
                login_user(user)
                session.pop("tema_atual", None)
                return jsonify({"status": "sucesso"})
            
            # Formulário tradicional
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
    except Exception:
        print(traceback.format_exc())
        return render_template("login.html", erro="Erro interno no servidor."), 500

@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    try:
        foto_padrao = "https://img.freepik.com/psd-gratuitas/ilustracao-3d-de-uma-pessoa-com-oculos-de-sol_23-2149436188.jpg"

        if request.method == "POST":
            if request.is_json:
                data = request.get_json()
                if not data:
                    return jsonify({"status": "erro", "mensagem": "JSON inválido."}), 400
                
                nome = data.get("nome")
                email = data.get("email")
                
                if not nome or not email:
                    return jsonify({"status": "erro", "mensagem": "Dados incompletos."}), 400
                
                usuario_existente = Usuario.query.filter_by(email=email).first()
                if usuario_existente:
                    login_user(usuario_existente)
                    session.pop("tema_atual", None)
                    return jsonify({"status": "sucesso"})
                
                senha_fake = generate_password_hash("google_login")
                novo_usuario = Usuario(nome=nome, email=email, senha=senha_fake, foto=foto_padrao)
                db.session.add(novo_usuario)
                db.session.commit()
                login_user(novo_usuario)
                session.pop("tema_atual", None)
                return jsonify({"status": "sucesso"})
            
            # Formulário tradicional
            nome = request.form.get("nome")
            email = request.form.get("email")
            senha = request.form.get("senha")

            if not nome or not email or not senha:
                return render_template("registrar.html", erro="Todos os campos são obrigatórios.")

            if Usuario.query.filter_by(email=email).first():
                return render_template("registrar.html", erro="Email já cadastrado.")

            senha_hash = generate_password_hash(senha)
            novo_usuario = Usuario(nome=nome, email=email, senha=senha_hash, foto=foto_padrao)
            db.session.add(novo_usuario)
            db.session.commit()
            login_user(novo_usuario)
            session.pop("tema_atual", None)
            return redirect(url_for("chat"))
        
        return render_template("registrar.html")
    except Exception:
        print(traceback.format_exc())
        return render_template("registrar.html", erro="Erro interno no servidor."), 500
@app.route('/trocarfoto')
def trocarfoto():
    return render_template("fotos_perfil.html")


@app.route('/foto1', methods=["POST"])
@login_required
def foto1():
    foto_url = 'https://th.bing.com/th/id/OIP.3LAs0OmHf4EPhBAg5doekQHaHa?pid=ImgDet&w=201&h=201&c=7'
    
    current_user.foto = foto_url
    db.session.commit()
    
    return redirect(url_for('perfil'))



@app.route('/foto2', methods=["POST"])
@login_required
def foto2():
    foto_url = 'https://th.bing.com/th/id/OIP.LthmDz9q8FVAk3dDHqnKkAHaHa?w=197&h=197&c=7&r=0&o=5&pid=1.7'
    
    current_user.foto = foto_url
    db.session.commit()
    
    return redirect(url_for('perfil'))


@app.route('/foto3', methods=["POST"])
@login_required
def foto3():
    foto_url = 'https://th.bing.com/th/id/OIP.L2XmG_rXdrp-lKDU7EVygQHaHa?w=174&h=180&c=7&r=0&o=5&pid=1.7'
    
    current_user.foto = foto_url
    db.session.commit()
    
    return redirect(url_for('perfil'))


@app.route('/foto4', methods=["POST"])
@login_required
def foto4():
    foto_url = 'data:image/jpeg;base64,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'
    
    current_user.foto = foto_url
    db.session.commit()
    
    return redirect(url_for('perfil'))

@app.route('/foto5', methods=["POST"])
@login_required
def foto5():
    foto_url = 'https://th.bing.com/th/id/OIP.MvFmQWBYDxZ6IB74D3OTHQHaHa?pid=ImgDet&w=203&h=203&c=7'
    
    current_user.foto = foto_url
    db.session.commit()
    
    return redirect(url_for('perfil'))


@app.route('/foto6', methods=["POST"])
@login_required
def foto6():
    foto_url = 'https://img.freepik.com/fotos-premium/ilustracao-3d-de-avatar-ou-perfil-de-personagem-de-desenho-animado_1183071-150.jpg'
    
    current_user.foto = foto_url
    db.session.commit()
    
    return redirect(url_for('perfil'))
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
        foto=current_user.foto,
        nome_usuario=current_user.nome,
        email_usuario=current_user.email,
        localizacao_usuario=getattr(current_user, "localizacao", "Não definida"))


@app.route('/trocarfoto1', methods=["GET" ,"POST"])
def trocarfoto1():
    return redirect(url_for('trocarfoto'))


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
        foto=current_user.foto,
        nome_usuario=current_user.nome,
        email_usuario=current_user.email,
        localizacao_usuario=getattr(current_user, "localizacao", "Não definida"))

@app.route('/perfil')
@login_required
def perfil():
    return render_template(
        'perfil.html',
        foto=current_user.foto,  # pega a foto do usuário logado                  
        nome_usuario=current_user.nome,
        email_usuario=current_user.email,
        localizacao_usuario=getattr(current_user, "localizacao", "Não definida")
    )

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
