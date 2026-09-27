package pt.pereirabmd.resumo;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * Corre em segundo plano (periódico, WorkManager) e sempre que o utilizador toca no botão de atualizar.
 * Busca as 4 APIs com um único token silencioso, guarda os textos em SharedPreferences (a fonte que o
 * widget lê) e pede ao widget para se redesenhar. Uma app que falhe não impede as outras — cada uma
 * guarda o seu próprio erro em vez de travar o resumo inteiro.
 */
public class RefreshWorker extends Worker {
    private static final String TAG = "ResumoWorker";

    public RefreshWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        Context context = getApplicationContext();
        SharedPreferences prefs = context.getSharedPreferences(Config.PREFS, Context.MODE_PRIVATE);
        String token = AuthHelper.tokenSilencioso(context, 20);
        if (token == null) {
            prefs.edit().putBoolean("autorizado", false).apply();
            ResumoWidgetProvider.atualizarTodos(context);
            return Result.success();   // sem interação não há como continuar; o utilizador tem de reabrir a app
        }
        SharedPreferences.Editor editor = prefs.edit();
        editor.putBoolean("autorizado", true);
        editor.putString("tarefas", tentar("Tarefas", () -> ResumoData.tarefas(token)));
        editor.putString("bilhetes", tentar("Bilhetes", () -> ResumoData.bilhetes(token)));
        editor.putString("rto", tentar("RTO", () -> ResumoData.rto(token)));
        editor.putString("financas", tentar("Finanças", () -> ResumoData.financas(token)));
        editor.putString("atualizado_em", LocalDateTime.now().format(DateTimeFormatter.ofPattern("HH:mm")));
        editor.apply();
        ResumoWidgetProvider.atualizarTodos(context);
        return Result.success();
    }

    private interface Busca {
        String obter() throws Exception;
    }

    private static String tentar(String nome, Busca busca) {
        try {
            return busca.obter();
        } catch (Exception e) {
            Log.e(TAG, nome + ": falha a atualizar", e);
            return "Não foi possível atualizar";
        }
    }
}
