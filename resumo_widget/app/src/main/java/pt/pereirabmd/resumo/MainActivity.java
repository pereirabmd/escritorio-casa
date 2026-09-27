package pt.pereirabmd.resumo;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;

import androidx.work.ExistingWorkPolicy;
import androidx.work.OneTimeWorkRequest;
import androidx.work.WorkManager;

/** Único ecrã da app: um botão para autorizar o acesso Google (uma vez) e o estado atual. O widget em si
 * vive só no ecrã inicial — este ecrã não mostra dados, só trata do login que o widget não consegue pedir
 * sozinho (widgets não têm interface interativa). */
public class MainActivity extends Activity {
    private TextView textoEstado;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        textoEstado = findViewById(R.id.texto_estado);
        Button botao = findViewById(R.id.botao_autorizar);
        botao.setOnClickListener(v -> autorizar());
        atualizarEstadoTexto();
    }

    private void autorizar() {
        textoEstado.setText("A abrir o consentimento da Google…");
        AuthHelper.autorizarInterativo(this, new AuthHelper.Resultado() {
            @Override
            public void sucesso(String accessToken) {
                marcarAutorizadoEAtualizar();
            }

            @Override
            public void falhou(Exception erro) {
                textoEstado.setText("Não foi possível autorizar: " + erro.getMessage());
            }
        });
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == AuthHelper.REQUEST_CODE) {
            if (data == null) {
                textoEstado.setText("Autorização cancelada.");
                return;
            }
            AuthHelper.tratarResultadoActivity(this, data, new AuthHelper.Resultado() {
                @Override
                public void sucesso(String accessToken) {
                    marcarAutorizadoEAtualizar();
                }

                @Override
                public void falhou(Exception erro) {
                    textoEstado.setText("Autorização recusada ou cancelada.");
                }
            });
        }
    }

    private void marcarAutorizadoEAtualizar() {
        getSharedPreferences(Config.PREFS, MODE_PRIVATE).edit().putBoolean("autorizado", true).apply();
        WorkManager.getInstance(this).enqueueUniqueWork(
                Config.WORK_UNICO, ExistingWorkPolicy.REPLACE, new OneTimeWorkRequest.Builder(RefreshWorker.class).build());
        textoEstado.setText("Autorizado! Adiciona o widget \"Resumo\" ao ecrã inicial (toca sem soltar no ecrã inicial → Widgets).");
    }

    private void atualizarEstadoTexto() {
        SharedPreferences prefs = getSharedPreferences(Config.PREFS, MODE_PRIVATE);
        if (prefs.getBoolean("autorizado", false)) {
            textoEstado.setText("Já autorizado. Adiciona o widget \"Resumo\" ao ecrã inicial, se ainda não o fizeste.");
        }
    }
}
