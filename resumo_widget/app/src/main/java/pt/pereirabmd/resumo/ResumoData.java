package pt.pereirabmd.resumo;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

/**
 * Um resumo de uma linha por app, a partir das mesmas APIs que as PWAs usam. As regras de negócio exatas
 * de cada app (o que conta como "atrasada", etc.) ficam no servidor — aqui só se conta/soma o que já vem
 * calculado ou filtrado. A data "hoje" usa o fuso do telefone: se viajares para outro fuso o resumo pode
 * desviar-se de um dia até voltares a abrir a app (aceitável para um resumo, não para as compras).
 */
final class ResumoData {
    private ResumoData() {}

    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_LOCAL_DATE;
    private static final DateTimeFormatter CURTA = DateTimeFormatter.ofPattern("dd/MM", Locale.forLanguageTag("pt-PT"));

    static String tarefas(String token) throws IOException, org.json.JSONException {
        JSONObject dados = ApiClient.get(Config.URL_TAREFAS, token);
        JSONArray instancias = dados.getJSONArray("instancias");
        String hoje = LocalDate.now().format(ISO);
        int atrasadas = 0, hojeCount = 0;
        for (int i = 0; i < instancias.length(); i++) {
            JSONObject inst = instancias.getJSONObject(i);
            String estado = inst.optString("estado", "");
            if ("Atrasada".equals(estado)) atrasadas++;
            else if ("Pendente".equals(estado) && hoje.equals(inst.optString("data", ""))) hojeCount++;
        }
        if (atrasadas > 0 && hojeCount > 0) return atrasadas + " atrasada(s), " + hojeCount + " hoje";
        if (atrasadas > 0) return atrasadas + " tarefa(s) atrasada(s)";
        if (hojeCount > 0) return hojeCount + " tarefa(s) hoje";
        return "Tudo em dia";
    }

    static String bilhetes(String token) throws IOException, org.json.JSONException {
        JSONObject dados = ApiClient.get(Config.URL_BILHETES, token);
        String hoje = LocalDate.now().format(ISO);
        JSONObject proxima = maisProxima(dados.getJSONArray("compras"), hoje, "data", "hora");
        boolean confirmada = proxima != null;
        if (proxima == null) proxima = maisProxima(filtrarAtivas(dados.getJSONArray("viagens")), hoje, "data", "hora");
        if (proxima == null) return "Sem viagens marcadas";
        String quando = formatarData(proxima.optString("data", "")) + " " + proxima.optString("hora", "");
        String percurso = abreviar(proxima.optString("origem", "")) + "→" + abreviar(proxima.optString("destino", ""));
        return quando + " · " + percurso + (confirmada ? "" : " (por comprar)");
    }

    static String rto(String token) throws IOException, org.json.JSONException {
        LocalDate hoje = LocalDate.now(), amanha = hoje.plusDays(1);
        String url = Config.URL_RTO + "?desde=" + hoje.format(ISO) + "&ate=" + amanha.format(ISO);
        JSONObject dados = ApiClient.get(url, token);
        JSONObject dias = dados.getJSONObject("dias");
        String hojeTxt = nomeMarca(dias.optString(hoje.format(ISO), ""));
        String amanhaTxt = nomeMarca(dias.optString(amanha.format(ISO), ""));
        if (hojeTxt == null && amanhaTxt == null) return "Sem marcação";
        StringBuilder sb = new StringBuilder();
        if (hojeTxt != null) sb.append("Hoje ").append(hojeTxt);
        if (amanhaTxt != null) sb.append(sb.length() > 0 ? " · " : "").append("Amanhã ").append(amanhaTxt);
        return sb.toString();
    }

    static String financas(String token) throws IOException, org.json.JSONException {
        String mes = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy-MM"));
        String hoje = LocalDate.now().format(ISO);
        String url = Config.URL_FINANCAS + "?mes=" + mes + "&pendentes=1";
        JSONObject dados = ApiClient.get(url, token);
        JSONArray lancamentos = dados.getJSONArray("lancamentos");
        double total = 0;
        int vencidas = 0;
        for (int i = 0; i < lancamentos.length(); i++) {
            JSONObject l = lancamentos.getJSONObject(i);
            if (!"despesa".equals(l.optString("tipo"))) continue;
            total += l.optDouble("valor", 0);
            if (l.optString("data_vencimento", "").compareTo(hoje) < 0) vencidas++;
        }
        if (total <= 0) return "Tudo pago este mês";
        String valor = String.format(Locale.forLanguageTag("pt-PT"), "%.2f €", total);
        return vencidas > 0 ? vencidas + " vencida(s) · " + valor + " por pagar" : valor + " por pagar";
    }

    // --- auxiliares ---------------------------------------------------------

    private static JSONArray filtrarAtivas(JSONArray viagens) throws org.json.JSONException {
        JSONArray out = new JSONArray();
        for (int i = 0; i < viagens.length(); i++) {
            JSONObject v = viagens.getJSONObject(i);
            if ("SIM".equals(v.optString("ativo"))) out.put(v);
        }
        return out;
    }

    /** A primeira entrada (data,horaCampo) que seja hoje ou no futuro, já ordenada pelo servidor. */
    private static JSONObject maisProxima(JSONArray itens, String hoje, String campoData, String campoHora) throws org.json.JSONException {
        JSONObject melhor = null;
        for (int i = 0; i < itens.length(); i++) {
            JSONObject it = itens.getJSONObject(i);
            String data = it.optString(campoData, "");
            if (data.compareTo(hoje) < 0) continue;
            if (melhor == null || data.compareTo(melhor.optString(campoData, "")) < 0
                    || (data.equals(melhor.optString(campoData, "")) && it.optString(campoHora, "").compareTo(melhor.optString(campoHora, "")) < 0)) {
                melhor = it;
            }
        }
        return melhor;
    }

    private static String formatarData(String iso) {
        try {
            LocalDate d = LocalDate.parse(iso);
            if (d.equals(LocalDate.now())) return "Hoje";
            if (d.equals(LocalDate.now().plusDays(1))) return "Amanhã";
            return d.format(CURTA);
        } catch (Exception e) {
            return iso;
        }
    }

    private static String abreviar(String estacao) {
        if (estacao.length() <= 12) return estacao;
        return estacao.substring(0, 11) + "…";
    }

    private static String nomeMarca(String marca) {
        if ("T".equals(marca)) return "Escritório";
        if ("C".equals(marca)) return "Casa";
        return null;
    }
}
