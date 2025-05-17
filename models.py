from db import db
from flask_login import UserMixin

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
   
    senha = db.Column(db.String(200), nullable=False)

    mensagens = db.relationship('Mensagem', backref='usuario', lazy=True)

    def __repr__(self):
        return f'<Usuario {self.nome}>'

    def get_id(self):
        return str(self.id)


class QA(db.Model):
    __tablename__ = 'qa'
    id = db.Column(db.Integer, primary_key=True)
    pergunta = db.Column(db.String(200), nullable=False)
    resposta = db.Column(db.String(200), nullable=False)


class Mensagem(db.Model):
    __tablename__ = 'mensagens'
    id = db.Column(db.Integer, primary_key=True)
    conteudo = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(50), default='texto')  # ex: texto, imagem, áudio
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
