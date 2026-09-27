package pt.pereirabmd.resumo;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

import org.json.JSONObject;

/** GET autenticado à API do Pi (dados/api.py) — só biblioteca padrão, sem OkHttp. */
final class ApiClient {
    private ApiClient() {}

    static JSONObject get(String url, String accessToken) throws IOException {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod("GET");
        conn.setRequestProperty("Authorization", "Bearer " + accessToken);
        conn.setConnectTimeout(10_000);
        conn.setReadTimeout(15_000);
        try {
            int status = conn.getResponseCode();
            InputStream corpo = status >= 200 && status < 300 ? conn.getInputStream() : conn.getErrorStream();
            String texto = corpo == null ? "" : ler(corpo);
            if (status < 200 || status >= 300) {
                throw new IOException("HTTP " + status + " em " + url + ": " + texto.substring(0, Math.min(200, texto.length())));
            }
            try {
                return new JSONObject(texto);
            } catch (Exception e) {
                throw new IOException("resposta não é JSON válido: " + url, e);
            }
        } finally {
            conn.disconnect();
        }
    }

    private static String ler(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
        return out.toString(StandardCharsets.UTF_8.name());
    }
}
