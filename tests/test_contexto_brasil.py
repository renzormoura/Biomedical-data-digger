import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "biomedical-article-summariser"))

import contexto_brasil
import prompt_builders


class ContextoCuradoTest(unittest.TestCase):
    def test_bloco_contexto_inclui_fonte_e_codigo_quando_relevante(self):
        bloco = contexto_brasil.bloco_contexto("disponibilidade de medicamento no SUS")
        self.assertIn("CONTEXTO CURADO", bloco)
        self.assertIn("Fonte:", bloco)
        self.assertIn("atualizado em", bloco)

    def test_bloco_contexto_vazio_para_tema_irrelevante(self):
        bloco = contexto_brasil.bloco_contexto("algoritmo de aprendizado de maquina para imagens")
        self.assertEqual(bloco, "")

    def test_prompts_br_incluem_contexto_curado_e_marcao(self):
        resumo = "artigo sobre metformina e disponibilidade no SUS"
        sus = prompt_builders.build_message_disponibilidade_sus("Titulo", resumo)[1]["content"]
        self.assertIn("CONTEXTO CURADO", sus)
        self.assertIn("[CONTEXTO CURADO]", prompt_builders.build_message_aplicabilidade_br("Titulo", resumo)[1]["content"])
        self.assertIn("CONTEXTO CURADO", prompt_builders.build_message_vigilancia_sanitaria("Titulo", resumo)[1]["content"])

    def test_prompts_br_exigem_resposta_nao_verificavel(self):
        sus = prompt_builders.build_message_disponibilidade_sus("Titulo", "artigo sobre diabetes no SUS")[1]["content"]
        self.assertIn("verificável com as fontes acessíveis", sus)
        self.assertIn("Nunca use memória externa", sus)


class VerificacaoExternaTest(unittest.TestCase):
    def setUp(self):
        self.verificador = contexto_brasil.VerificacaoExterna()

    def test_url_insegura_e_rejeitada(self):
        for url in ("file:///etc/passwd", "ftp://exemplo.com/x", "javascript:alert(1)", ""):
            resultado = self.verificador.consultar(url)
            self.assertEqual(resultado["status"], "nao_verificavel")

    def test_falha_de_rede_vira_status_explicito(self):
        resultado = self.verificador.consultar("http://dominio-inexistente-xyz.invalid/")
        self.assertEqual(resultado["status"], "nao_verificavel")
        self.assertIn("motivo", resultado)

    def test_relatorio_marca_nao_verificavel(self):
        relatorio = contexto_brasil.relatorio_verificacao([
            {"status": "nao_verificavel", "motivo": "timeout", "url": "https://exemplo.gov.br"},
        ])
        self.assertIn("NAO VERIFICAVEL", relatorio)
        self.assertIn("timeout", relatorio)

    def test_catalogo_somente_urls_http_validas(self):
        for fonte in contexto_brasil.VERIFICATION_SOURCES.values():
            self.assertTrue(fonte["catalog_url"].startswith("https://"))
            self.assertIn("updated", fonte)


if __name__ == "__main__":
    unittest.main()
