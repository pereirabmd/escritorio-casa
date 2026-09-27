package pt.pereirabmd.resumo;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import com.google.android.gms.auth.api.identity.AuthorizationClient;
import com.google.android.gms.auth.api.identity.AuthorizationRequest;
import com.google.android.gms.auth.api.identity.AuthorizationResult;
import com.google.android.gms.auth.api.identity.Identity;
import com.google.android.gms.common.api.ApiException;
import com.google.android.gms.common.api.Scope;
import com.google.android.gms.tasks.Task;
import com.google.android.gms.tasks.Tasks;

import java.util.Collections;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Autenticação Google via Identity Services para Android (Authorization API). Pede só o scope "email" —
 * o suficiente para a API do Pi validar o token (mesma verificação que já usa para as PWAs: tokeninfo,
 * aud, email_verified). Não guardamos o token: cada pedido de dados pede um novo, silenciosamente, uma
 * vez que a autorização já tenha sido dada uma vez pelo utilizador.
 *
 * Nota: a app tem de estar registada como cliente OAuth "Android" na mesma consola Google Cloud do
 * projeto (pacote pt.pereirabmd.resumo + SHA-1 da chave de assinatura) — ver README.md desta pasta.
 */
final class AuthHelper {
    private static final String TAG = "ResumoAuth";

    private AuthHelper() {}

    private static AuthorizationRequest request() {
        return AuthorizationRequest.builder()
                .setRequestedScopes(Collections.singletonList(new Scope("email")))
                .build();
    }

    /** Chamado a partir de um Activity: pede a autorização de forma interativa (mostra o seletor de conta
     * e o consentimento, só da primeira vez). O resultado chega a {@code onResult}. */
    static void autorizarInterativo(Activity activity, Resultado onResult) {
        AuthorizationClient client = Identity.getAuthorizationClient(activity);
        client.authorize(request())
                .addOnSuccessListener(result -> {
                    if (result.hasResolution()) {
                        try {
                            activity.startIntentSenderForResult(
                                    result.getPendingIntent().getIntentSender(), REQUEST_CODE, null, 0, 0, 0, null);
                        } catch (Exception e) {
                            Log.e(TAG, "não consegui abrir o ecrã de autorização", e);
                            onResult.falhou(e);
                        }
                    } else {
                        onResult.sucesso(result.getAccessToken());
                    }
                })
                .addOnFailureListener(e -> {
                    Log.e(TAG, "autorização falhou", e);
                    onResult.falhou(e);
                });
    }

    static final int REQUEST_CODE = 4321;

    /** Chamado a partir de {@code Activity#onActivityResult} depois do ecrã de consentimento. */
    static void tratarResultadoActivity(Activity activity, Intent data, Resultado onResult) {
        try {
            AuthorizationResult result = Identity.getAuthorizationClient(activity).getAuthorizationResultFromIntent(data);
            onResult.sucesso(result.getAccessToken());
        } catch (ApiException e) {
            Log.e(TAG, "autorização recusada ou cancelada", e);
            onResult.falhou(e);
        }
    }

    /** Pedido silencioso, para correr em segundo plano (RefreshWorker). Bloqueia a thread chamadora —
     * nunca invocar a partir da thread principal. Devolve {@code null} se precisar de interação (o
     * utilizador tem de voltar a abrir a app), sem levantar exceção nesse caso. */
    static String tokenSilencioso(Context context, long timeoutSegundos) {
        try {
            Task<AuthorizationResult> tarefa = Identity.getAuthorizationClient(context).authorize(request());
            AuthorizationResult result = Tasks.await(tarefa, timeoutSegundos, TimeUnit.SECONDS);
            if (result.hasResolution()) {
                Log.w(TAG, "autorização precisa de interação (por reautorizar): abre a app Resumo");
                return null;
            }
            return result.getAccessToken();
        } catch (ExecutionException | InterruptedException | TimeoutException e) {
            Log.e(TAG, "não consegui obter um token em segundo plano", e);
            return null;
        }
    }

    interface Resultado {
        void sucesso(String accessToken);
        void falhou(Exception erro);
    }
}
