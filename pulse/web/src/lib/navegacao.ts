/** Sai da aplicação para um endereço externo (ex.: o consentimento da Google). À parte para se poder simular nos testes. */
export const irPara = (url: string) => window.location.assign(url)
