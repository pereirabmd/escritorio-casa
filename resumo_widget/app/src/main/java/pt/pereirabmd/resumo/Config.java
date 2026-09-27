package pt.pereirabmd.resumo;

/** Constantes partilhadas. A API e as URLs são as mesmas que as PWAs já usam (ver dados/api.py). */
final class Config {
    private Config() {}

    static final String API_BASE = "https://bmdpereira.duckdns.org/dados-api";

    static final String URL_TAREFAS = API_BASE + "/tarefas/dados";
    static final String URL_BILHETES = API_BASE + "/bilhetes/dados";
    static final String URL_RTO = API_BASE + "/rto/dias";
    static final String URL_FINANCAS = API_BASE + "/financas/lancamentos";

    static final String APP_TAREFAS = "https://pereirabmd.github.io/escritorio-casa/tarefas/";
    static final String APP_BILHETES = "https://pereirabmd.github.io/escritorio-casa/bilhetes_cp/";
    static final String APP_RTO = "https://pereirabmd.github.io/escritorio-casa/RTO/";
    static final String APP_FINANCAS = "https://pereirabmd.github.io/escritorio-casa/financas/";

    static final String PREFS = "resumo_prefs";
    static final String WORK_PERIODICO = "resumo_refresh_periodico";
    static final String WORK_UNICO = "resumo_refresh_unico";
}
