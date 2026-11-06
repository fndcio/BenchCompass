# PRIVACY

Local-first: veriler varsayılan olarak yerelde kalır.
- `benchmark_history.db` ve ölçümler repoya/paylaşıma girmez.
- Telemetri varsayılan kapalıdır.
- Paylaşım endpoints'lerinde yalnızca seçili alanlar gönderilir; kullanıcı adı, hostname, IP, tam yol hariç tutulur (bkz. `config/share_config.json`).
- Public seed verilerde topluluk kullanıcı katkıları (ad/prompt/çıktı) tutulmaz.
