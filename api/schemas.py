"""Pydantic modelleri — frontend ile backend arasindaki tip guclu kontrat.

Sprint 3 ile gelen donusum: daha once dict olarak tasinmayan yapilsal alanlar
(required_vram_gb, required_ram_gb, quantization, param_count_b,
context_length_supported, context_length_estimated_at, estimated_speed_tok_s)
 artik ModelRecord'in birer uyesidir. Bunlar 'notes' metninden regex ile
cikarilir (bkz. notes_parser.py) ve SQLite'a yeni sutun olarak yazilir.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# --- Donanim profili --------------------------------------------------------


class HardwareProfileEntry(BaseModel):
    """Tek bir cihaz profili (gaming PC, masaüstü PC, vb.)."""

    id: str
    device_name: str
    cpu: str | None = None
    npu_tops: int | None = None
    gpu: str | None = None
    vram_gb: float
    ram_gb: float
    storage_gb: int | None = None
    os: str | None = None
    cuda_version: str | None = None


class TierThresholds(BaseModel):
    """Bolum 2.2'deki tier formulu icin esik degerleri (GB cinsinden).

    - vram_full_margin: 'Tam Uyumlu' icin VRAM uzerinde birakilmesi gereken pay
    - ram_full_margin : 'Tam Uyumlu' icin RAM uzerinde birakilmasi gereken pay
    - vram_caution_margin: 'Dikkatli Kullan' icin alt sinir (CPU offload payi)
    """

    vram_full_margin: float = Field(default=2.0)
    ram_full_margin: float = Field(default=4.0)
    vram_caution_margin: float = Field(default=-1.5)


class HardwareConfig(BaseModel):
    """config/hardware_profile.json'un tam serilestirme modeli."""

    active_profile: str
    profiles: list[HardwareProfileEntry]
    tier_thresholds: TierThresholds = Field(default_factory=TierThresholds)

    def active(self) -> HardwareProfileEntry:
        """Aktif profili dondurur; yoksa ilk profili dondurur."""
        for p in self.profiles:
            if p.id == self.active_profile:
                return p
        return self.profiles[0]


class HardwareUpdate(BaseModel):
    """PUT /api/hardware ile gonderilen kismi guncelleme govdesi."""

    active_profile: str | None = None
    profiles: list[HardwareProfileEntry] | None = None
    tier_thresholds: TierThresholds | None = None


# --- Model kaydi ------------------------------------------------------------


class ModelRecord(BaseModel):
    """benchmark_models tablosunun bir satiri.

    Sprint 3 oncesi sadece ilk 6 alan vardi (name..notes). Geri kalan 7 alan
    migrasyon ile eklenir ve 'notes' metninden backfill edilir.
    """

    # Orijinal alanlar (geri donuk uyumlu)
    id: int | None = None
    run_id: int | None = None
    name: str
    provider: str = "-"
    use_case: str = "-"
    fit_score: float = 0.0
    context_window: int = 0
    notes: str | list | dict | None = None
    # Sprint 3 ile eklenen yapilsal alanlar (notes'tan cikarildi)
    required_vram_gb: float | None = None
    required_ram_gb: float | None = None
    context_length_supported: int | None = None
    context_length_estimated_at: int | None = None
    quantization: str | None = None
    param_count_b: float | None = None
    estimated_speed_tok_s: float | None = None
    # Not tabanli ipuclari (DB'ye yazilmaz ama frontend/backend tier icin kullanilir)
    loaded_into_vram: bool = False
    insufficient: bool = False
    # Sprint 08: MoE (Mixture-of-Experts) mimari alanlari
    is_moe: bool = False
    active_params_b: float | None = None
    total_params_b: float | None = None
    # Sprint 12: calisma modu (GPU / CPU_offload / Mixed / CPU) — tier formulune dahil
    run_mode: str = ""


# --- Uyumluluk sonucu -------------------------------------------------------


class TierResult(BaseModel):
    """Bir model icin hesaplanan tier ve tooltip icin detaylar.

    Tier DB'ye YAZILMAZ — her render'da (backend veya frontend) donanim
    profili ile yeniden hesaplanir. Boylece kullanici Ayarlar'dan donanimini
    degistirirse gecmis veriler de dogru tier ile gosterilir.
    """

    tier: str  # "Tam Uyumlu" | "Uyumlu (Sinirda)" | "Dikkatli Kullan" | "Uygun Degil"
    tone: str  # "good" | "warn" | "orange" | "bad"
    vram_margin_gb: float | None = None
    ram_margin_gb: float | None = None
    context_flag: str | None = None
    tooltip: str = ""
    explanation: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    verify_cmd: str = ""


# --- API cevap zarflari -----------------------------------------------------


class DashboardSummary(BaseModel):
    source: str
    latest: dict
    history: list[dict]


class SnapshotResult(BaseModel):
    ok: bool
    run_id: int
    copied_models: int


class MigrateResult(BaseModel):
    ok: bool
    added_columns: list[str]
    backfilled_rows: int = 0


# --- Multi-Runtime Provider (Sprint 09) -------------------------------------


class RuntimeInfo(BaseModel):
    id: str
    name: str
    description: str
    default_port: int


class ProviderConfig(BaseModel):
    active_provider: str = "auto"
    ollama_host: str = "http://localhost:11434"
    lmstudio_host: str = "http://localhost:1234"
    llamacpp_host: str = "http://localhost:8080"
    mlx_host: str = "http://localhost:8080"
