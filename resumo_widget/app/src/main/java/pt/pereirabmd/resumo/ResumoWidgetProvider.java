package pt.pereirabmd.resumo;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.widget.RemoteViews;

import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.ExistingWorkPolicy;
import androidx.work.OneTimeWorkRequest;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;

import java.util.concurrent.TimeUnit;

/** O widget em si: só desenha o que já está em SharedPreferences (rápido, sem rede) e delega a busca de
 * dados ao RefreshWorker — nunca faz pedidos de rede aqui (o AppWidgetProvider corre no processo principal
 * e um pedido lento bloquearia o sistema). */
public class ResumoWidgetProvider extends AppWidgetProvider {
    private static final String ACTION_REFRESH = "pt.pereirabmd.resumo.ACTION_REFRESH";

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] appWidgetIds) {
        for (int id : appWidgetIds) manager.updateAppWidget(id, construirViews(context));
        agendarUmaVez(context);
    }

    @Override
    public void onEnabled(Context context) {
        PeriodicWorkRequest pedido = new PeriodicWorkRequest.Builder(RefreshWorker.class, 30, TimeUnit.MINUTES).build();
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(Config.WORK_PERIODICO, ExistingPeriodicWorkPolicy.KEEP, pedido);
    }

    @Override
    public void onDisabled(Context context) {
        WorkManager.getInstance(context).cancelUniqueWork(Config.WORK_PERIODICO);
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        if (ACTION_REFRESH.equals(intent.getAction())) agendarUmaVez(context);
    }

    private static void agendarUmaVez(Context context) {
        OneTimeWorkRequest pedido = new OneTimeWorkRequest.Builder(RefreshWorker.class).build();
        WorkManager.getInstance(context).enqueueUniqueWork(Config.WORK_UNICO, ExistingWorkPolicy.KEEP, pedido);
    }

    /** Chamado pelo RefreshWorker depois de guardar dados novos, para todas as instâncias do widget. */
    static void atualizarTodos(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        int[] ids = manager.getAppWidgetIds(new android.content.ComponentName(context, ResumoWidgetProvider.class));
        RemoteViews views = construirViews(context);
        for (int id : ids) manager.updateAppWidget(id, views);
    }

    private static RemoteViews construirViews(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(Config.PREFS, Context.MODE_PRIVATE);
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_resumo);
        boolean autorizado = prefs.getBoolean("autorizado", false);

        if (!autorizado && !prefs.contains("tarefas")) {
            views.setTextViewText(R.id.texto_tarefas, "Toca para autorizar (abre a app)");
            views.setTextViewText(R.id.texto_bilhetes, "");
            views.setTextViewText(R.id.texto_rto, "");
            views.setTextViewText(R.id.texto_financas, "");
        } else {
            views.setTextViewText(R.id.texto_tarefas, prefs.getString("tarefas", "…"));
            views.setTextViewText(R.id.texto_bilhetes, prefs.getString("bilhetes", "…"));
            views.setTextViewText(R.id.texto_rto, prefs.getString("rto", "…"));
            views.setTextViewText(R.id.texto_financas, prefs.getString("financas", "…"));
        }
        String hora = prefs.getString("atualizado_em", null);
        views.setTextViewText(R.id.widget_atualizado, hora == null ? "" : ("Atualizado " + hora));

        views.setInt(R.id.icone_tarefas, "setColorFilter", context.getColor(R.color.tarefas));
        views.setInt(R.id.icone_bilhetes, "setColorFilter", context.getColor(R.color.bilhetes));
        views.setInt(R.id.icone_rto, "setColorFilter", context.getColor(R.color.rto));
        views.setInt(R.id.icone_financas, "setColorFilter", context.getColor(R.color.financas));

        views.setOnClickPendingIntent(R.id.linha_tarefas, abrirApp(context, Config.APP_TAREFAS, 1));
        views.setOnClickPendingIntent(R.id.linha_bilhetes, abrirApp(context, Config.APP_BILHETES, 2));
        views.setOnClickPendingIntent(R.id.linha_rto, abrirApp(context, Config.APP_RTO, 3));
        views.setOnClickPendingIntent(R.id.linha_financas, abrirApp(context, Config.APP_FINANCAS, 4));

        if (!autorizado) {
            views.setOnClickPendingIntent(R.id.widget_titulo, abrirAppPrincipal(context));
        }
        views.setOnClickPendingIntent(R.id.widget_refresh, atualizarAgora(context));
        return views;
    }

    private static PendingIntent abrirApp(Context context, String url, int requestCode) {
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
        return PendingIntent.getActivity(context, requestCode, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private static PendingIntent abrirAppPrincipal(Context context) {
        Intent intent = new Intent(context, MainActivity.class);
        return PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private static PendingIntent atualizarAgora(Context context) {
        Intent intent = new Intent(context, ResumoWidgetProvider.class).setAction(ACTION_REFRESH);
        return PendingIntent.getBroadcast(context, 5, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
}
