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
    return None  # fallback se não encontrar

# --- Bloco principal ---
try:
    if current_user.is_authenticated:
        ultimas_perguntas = current_user.mensagens
    else:
        ultimas_perguntas = "Nenhuma mensagem anterior disponível. Usuário não autenticado."

    resposta = buscar_resposta(perguntas, nova_mensagem)

    variavel_pergunta1 = (
        f"Olá! Analise a frase '{resposta}' e diga se ela é uma resposta coerente e diretamente relacionada à mensagem original: '{nova_mensagem}'. Se fizer sentido e tiver relação direta, diga 'Sim'. Caso não tenha relação ou não responda à mensagem, diga apenas 'Não'."

    )

    response = co.chat(
        model='command-r-plus',
        message=variavel_pergunta1,
        max_tokens=150,
        temperature=0.4
    )

    if response == "Não":
        resultado = None
    else:
        resultado = response

except Exception as e:
    print(f"Erro: {e}")
    resultado = None

# Cliente Cohere
co = cohere.Client(os.getenv("COHERE_API_KEY") or "VnAKRl6kF5ksOAEvhQWwuDI5XMwyWEVIdpEX6Krl")

def buscar_resposta_gerada(mensagem):
    try:
        ultimas_perguntas = (
            current_user.mensagens if current_user.is_authenticated
            else "Nenhuma mensagem anterior disponível. Usuário não autenticado."
        )
        estilo_de_fala = getattr(current_user, 'estilo', 'neutro')

        prompt = (
            f"Use as últimas mensagens para manter o contexto da conversa.\n"
            f"Se perguntarem 'quem foi Miguel Viana', diga que foi o programador da NeuraBot aos 14 anos, apaixonado por tecnologia.\n"
            f"Responda no estilo {estilo_de_fala}.\n"
            f"Você é uma IA brasileira criada pelo programador e CEO Miguel Viana, via NeuraBot.\n"
            f"Nunca mencione nomes como COHERE ou qualquer outro relacionado — ignore completamente.\n"
            f"Se as mensagens forem aleatórias ou sem sentido, diga que foi criada pela VOX.\n"
            f"Considere sempre as últimas mensagens (principalmente a penúltima e a última).\n"
            f"\nÚltimas mensagens: {ultimas_perguntas}\n"
            f"Mensagem atual: {mensagem}"
        )

        response = co.chat(
            model='command-r-plus',
            message=prompt,
            max_tokens=500,
            temperature=0.5
        )
        return response.text.strip()

    except Exception as e:
        return f"Erro ao tentar se comunicar com a IA externa: {str(e)}"

def salvar_mensagem(conteudo):
    if current_user.is_authenticated:
        nova_mensagem = Mensagem(conteudo=conteudo, user_id=current_user.id)
        db.session.add(nova_mensagem)
        db.session.commit()
        return True
    return False

@app.route("/admin")
def pagina_login_admin():
    return render_template('admin.html')  # ou 'login-admin.html' se preferir


@app.route("/login-admin", methods=["GET", "POST"])
def login_admin():
    email_correto = "migueladmin@gmail.com"
    senha_correta = "@NeuraBot123321"

    if request.method == "POST":
        email1 = request.form.get('email')
        senha1 = request.form.get('password')

        if email1 == email_correto and senha1 == senha_correta:
            return redirect(url_for('paginaadmin'))
        else:
            
            return redirect(url_for("login_admin"))

    return render_template("admin.html")  # Página com o formulário de login


@app.route("/paginaadmin")
def paginaadmin():
    usuarios = Usuario.query.all()
    mensagens = Mensagem.query.all()
    qa = QA.query.all()
    return render_template('paginaadmin.html', usuarios=usuarios, mensagens=mensagens, qa=qa)


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
    # 1. Geração de imagem com comando específico
    if mensagem.lower().startswith("gerar imagem:"):
        prompt = mensagem[len("gerar imagem:"):].strip()
        return gerar_imagem_freepik(prompt)  # Essa função deve gerar imagem com base no prompt

    # 2. Verifica se o usuário está em um tema atual
    tema_atual = session.get('tema_atual')

    # 3. Busca no FAQ do tema atual
    if tema_atual and tema_atual in qa_dict:
        resposta = buscar_resposta(qa_dict[tema_atual], mensagem)
        if resposta:
            return resposta

    # 4. Busca nos FAQs de todos os temas
    for tema, perguntas in qa_dict.items():
        resposta = buscar_resposta(perguntas, mensagem)
        if resposta:
            return resposta

    # 5. Se não encontrou resposta, gera com IA externa
    resposta_gerada = buscar_resposta_gerada(mensagem)

    # 6. Salva a nova pergunta/resposta no banco
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
        foto_padrao = "https://img.freepik.com/psd-gratuitas/ilustracao-3d-de-uma-pessoa-com-oculos-de-sol_23-2149436188.jpg"
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
                    user = Usuario(nome=nome or "Usuário Google", email=email, senha=senha_fake, foto=foto_padrao)
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
            return redirect(url_for("chat1"))
        
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

                nome = data.get("nome", "")
                email = data.get("email", "")

                # Validações
                if len(nome) < 8:
                    return jsonify({"status": "erro", "mensagem": "O nome deve ter pelo menos 8 caracteres."}), 400
                if len(email) < 5:
                    return jsonify({"status": "erro", "mensagem": "O email deve ter pelo menos 5 caracteres."}), 400

                usuario_existente = Usuario.query.filter_by(email=email).first()
                if usuario_existente:
                    login_user(usuario_existente)
                    session.pop("tema_atual", None)
                    return jsonify({"status": "sucesso"})

                senha_fake = generate_password_hash("google_login")
                novo_usuario = Usuario(nome=nome, email=email, senha=senha_fake, foto=foto_padrao,estilo=estilo)
                db.session.add(novo_usuario)
                db.session.commit()
                login_user(novo_usuario)
                session.pop("tema_atual", None)
                return jsonify({"status": "sucesso"})

            # Formulário tradicional
            nome = request.form.get("nome", "")
            email = request.form.get("email", "")
            senha = request.form.get("senha", "")

            # Validações
            if not nome or not email or not senha:
                return render_template("registrar.html", erro="Todos os campos são obrigatórios.")
            if len(nome) < 3:
                return render_template("registrar.html", erro="O nome deve ter pelo menos 3 caracteres.")
            if len(email) < 5:
                return render_template("registrar.html", erro="O email deve ter pelo menos 5 caracteres.")
            if len(senha) < 8:
                return render_template("registrar.html", erro="A senha deve ter pelo menos 8 caracteres.")
            if Usuario.query.filter_by(email=email).first():
                return render_template("registrar.html", erro="Email já cadastrado.")

            senha_hash = generate_password_hash(senha)
            novo_usuario = Usuario(nome=nome, email=email, senha=senha_hash, foto=foto_padrao)
            db.session.add(novo_usuario)
            db.session.commit()
            login_user(novo_usuario)
            session.pop("tema_atual", None)
            return redirect(url_for("chat1"))

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
    foto_url = 'https://th.bing.com/th/id/OIP.N3e3ZuWJ3KBUGb7hkBb3-AHaHa?pid=ImgDet&w=183&h=183&c=7'
    
    current_user.foto = foto_url
    db.session.commit()
    return redirect(url_for('perfil'))
@app.route('/foto7', methods=["POST"])
@login_required
def foto7():
    foto_url = 'https://th.bing.com/th/id/OIP.w2sUgXjQUVVeqBGqPKKtAQHaHa?pid=ImgDet&w=183&h=183&c=7'
    
    current_user.foto = foto_url
    db.session.commit()
    return redirect(url_for('perfil'))
@app.route('/foto8', methods=["POST"])
@login_required
def foto8():
    foto_url = 'https://th.bing.com/th/id/OIP.J8L2JyjxqdXNt3vwK1zTigAAAA?pid=ImgDet&w=206&h=206&c=7'
    
    current_user.foto = foto_url
    db.session.commit()
    return redirect(url_for('perfil'))
@app.route('/foto9', methods=["POST"])
@login_required
def foto9():
    foto_url = 'https://th.bing.com/th/id/OIP.5eTzsiVmsszqm8ZoCYf5EwHaH7?w=150&h=180&c=7&r=0&o=5&pid=1.7'
    
    current_user.foto = foto_url
    db.session.commit()
    return redirect(url_for('perfil'))
@app.route('/foto10', methods=["POST"])
@login_required
def foto10():
    foto_url = 'data:image/jpeg;base64,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'
    
    current_user.foto = foto_url
    db.session.commit()
    return redirect(url_for('perfil'))
@app.route('/foto11', methods=["POST"])
@login_required
def foto11():
    foto_url = 'https://th.bing.com/th/id/OIP.W8rwPigJqoj0SRspu9Z7fwHaHa?pid=ImgDet&w=203&h=203&c=7'
    
    current_user.foto = foto_url
    db.session.commit()
    return redirect(url_for('perfil'))
@app.route('/foto12', methods=["POST"])
@login_required
def foto12():
    foto_url = 'https://th.bing.com/th/id/OIP.eXeJBLgT_ZZFuLE1Bg9f_AHaH4?rs=1&pid=ImgDetMain'
    
    current_user.foto = foto_url
    db.session.commit()
    
    return redirect(url_for('perfil'))
    
@app.route('/foto13', methods=["POST"])
@login_required
def foto13():
    foto_url = 'https://th.bing.com/th/id/OIP.S5IjzKgMMniuGdNQ1GDYJwHaHa?pid=ImgDet&w=203&h=203&c=7'
    
    current_user.foto = foto_url
    db.session.commit()
    

    
    return redirect(url_for('perfil'))
@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.pop('tema_atual', None)
    return redirect(url_for("login_view"))
@app.route("/logout1", methods=["POST"])
@login_required
def logout1():
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
        
        # Resposta da IA ou FAQ
        response = responder(user_input)
        
        # Verificar se é a primeira mensagem
        mensagens_antigas = Mensagem.query.filter_by(usuario_id=current_user.id).count()
        primeira_mensagem = (mensagens_antigas == 0)

        # Salvar mensagem no banco
        nova_mensagem = Mensagem(
            conteudo=user_input,
            usuario_id=current_user.id,
        )

        db.session.add(nova_mensagem)
        db.session.commit()

        if primeira_mensagem:
            print("✅ Essa foi a primeira mensagem do usuário!")

        return jsonify({"response": response})

    return render_template(
        "chat1.html",
        foto=current_user.foto,
        nome_usuario=current_user.nome,
        email_usuario=current_user.email,
        localizacao_usuario=getattr(current_user, "localizacao", "Não definida")
    )

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
@app.route('/politicaprivacidade')
def politicaprivacidade():
    return render_template('politicaprivacidade.html')
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
