# GeekMagic SmallTV Ultra — Monitor de PC (sem trocar firmware)

Projeto para transformar um **GeekMagic SmallTV Ultra / ESP-12F (ESP8266)** em um monitor de PC usando **somente o firmware original**.

> **Objetivo:** não soldar, não trocar placa, não gravar firmware e não mexer no hardware.  
> O computador cria uma imagem 240×240 com as métricas e usa a API HTTP que o firmware original já possui para mostrar essa imagem na tela.

## O que aparece na tela

- Uso de CPU
- Uso de RAM
- Temperatura da CPU, quando disponível
- Uso/temperatura de GPU, quando disponível
- Ping
- Bateria do notebook
- Download/upload aproximados
- IP local
- Uptime

## Como funciona

```text
┌──────────────────────────┐
│      Notebook/PC         │
│                          │
│ psutil / ping / sensores │
└─────────────┬────────────┘
              │
              │ gera JPEG 240×240
              │ HTTP pela sua rede local
              ▼
┌──────────────────────────┐
│ GeekMagic SmallTV Ultra  │
│ ESP8266 + ST7789 240×240 │
│ firmware ORIGINAL        │
└──────────────────────────┘
```

O firmware original possui endpoints usados pela própria página de fotos:

```text
POST /doUpload?dir=/image/        -> envia imagem
GET  /set?theme=3                 -> modo de fotos
GET  /set?img=/image/arquivo.jpg  -> mostra a imagem
GET  /filelist?dir=/image         -> lista imagens
GET  /delete?file=/image/x.jpg    -> remove imagem
```

O script deste projeto utiliza apenas essas funções.

---

# 1. Antes de começar

## Hardware

Você já possui tudo que é necessário:

- GeekMagic SmallTV Ultra
- ESP-12F / ESP8266 interno
- Tela 240×240
- Cabo USB-C para alimentação
- PC/notebook Windows
- Ambos conectados à mesma rede Wi-Fi

**Não é necessário USB-TTL, solda, protoboard ou abrir o aparelho.**

## Software

Recomendado:

- Windows 10/11
- Python 3.10 ou superior

Confira:

```powershell
python --version
```

Se o comando `python` não existir, instale Python e marque **Add Python to PATH** durante a instalação.

---

# 2. Confirmar que o aparelho é acessível pela rede

Descubra o IP do SmallTV.

Há três formas simples:

1. abrir a página do roteador e procurar um dispositivo GeekMagic/ESP;
2. verificar o IP informado na interface de configuração do relógio;
3. usar o modo de descoberta deste projeto.

Depois de instalar as dependências:

```powershell
python src\pc_monitor.py --discover
```

Também é possível testar manualmente no navegador:

```text
http://IP_DO_SMALLTV/
```

Exemplo:

```text
http://192.168.1.42/
```

Se a interface do GeekMagic abrir, está tudo certo.

Você também pode testar:

```text
http://192.168.1.42/v.json
http://192.168.1.42/app.json
```

---

# 3. Instalação do projeto

Abra o PowerShell na pasta do projeto.

Crie um ambiente virtual:

```powershell
python -m venv .venv
```

Ative:

```powershell
.\.venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear scripts:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

Instale as dependências:

```powershell
pip install -r requirements.txt
```

---

# 4. Configuração

Copie:

```text
config.example.json
```

para:

```text
config.json
```

No PowerShell:

```powershell
Copy-Item config.example.json config.json
```

Abra `config.json` e altere principalmente:

```json
{
  "device_host": "192.168.1.42",
  "display_name": "PC MONITOR"
}
```

Use **somente o IP**, sem `http://`.

## Configurações importantes

### `push_interval_seconds`

Intervalo mínimo entre gravações de novas imagens no ESP8266.

O padrão é:

```json
"push_interval_seconds": 60
```

O firmware original salva as imagens na memória flash. Atualizar a tela várias vezes por segundo seria uma péssima ideia porque causaria muitas gravações na flash.

Para começar, use **60 segundos ou mais**.

### `bucket_cpu` e semelhantes

As métricas são arredondadas antes de gerar a imagem.

Exemplo:

```json
"bucket_cpu": 5
```

Assim, 52% e 54% podem gerar a mesma tela de 50%, evitando gravações desnecessárias.

---

# 5. Teste sem mexer no display

Primeiro veja se o Python consegue conversar com o aparelho:

```powershell
python src\pc_monitor.py --test
```

Você deverá ver algo parecido:

```text
SmallTV encontrado
Modelo: SmallTV-Ultra
Firmware: Ultra-V...
HTTP: OK
```

Esse comando **não envia nenhuma imagem**.

---

# 6. Gerar uma prévia no PC

Antes de enviar para o relógio:

```powershell
python src\pc_monitor.py --preview
```

Será criado:

```text
preview.jpg
```

Abra o arquivo e veja como ficará a tela.

---

# 7. Rodar o monitor

```powershell
python src\pc_monitor.py
```

O script:

1. lê CPU/RAM/bateria/rede;
2. mede o ping;
3. tenta ler sensores de temperatura;
4. gera uma tela de 240×240;
5. coloca o SmallTV em modo de imagem;
6. envia a imagem;
7. seleciona a imagem;
8. só cria outra quando houver mudança suficiente e o intervalo mínimo tiver passado.

Para parar:

```text
Ctrl + C
```

Por padrão, ao encerrar, o programa tenta voltar ao tema de clima original.

---

# 8. Temperatura da CPU/GPU no Windows

`psutil` geralmente não consegue ler temperatura no Windows sozinho.

Por isso o script possui suporte opcional ao **LibreHardwareMonitor**.

## Opção recomendada

1. instale/abra LibreHardwareMonitor;
2. execute-o como administrador;
3. mantenha-o aberto;
4. instale suporte WMI:

```powershell
pip install wmi pywin32
```

O monitor tentará automaticamente procurar sensores como:

```text
CPU Package
CPU Core
GPU Core
```

Se não encontrar sensores, a tela continuará funcionando normalmente e mostrará `--°C`.

Não é necessário LibreHardwareMonitor para CPU, RAM, ping, bateria e rede.

---

# 9. Personalização

No arquivo:

```text
src\pc_monitor.py
```

a função:

```python
render_frame(stats, config)
```

é responsável por toda a interface gráfica.

Você pode mudar:

- cores;
- fontes;
- tamanho das barras;
- quais métricas aparecem;
- título;
- posição dos elementos.

A imagem final precisa continuar com:

```text
240 × 240 pixels
```

---

# 10. Evitando desgaste da memória flash

Este ponto é importante.

O firmware original armazena fotos no filesystem da flash do ESP8266. Portanto, **não use esse método para animação em tempo real**.

O projeto reduz gravações de quatro maneiras:

1. arredonda valores;
2. não envia a mesma tela duas vezes;
3. impõe intervalo mínimo entre uploads;
4. mantém um pequeno cache de telas e reutiliza telas iguais.

Configuração recomendada para uso diário:

```json
{
  "push_interval_seconds": 60,
  "bucket_cpu": 5,
  "bucket_ram": 5,
  "bucket_temp": 2,
  "bucket_ping": 5,
  "max_cached_frames": 25
}
```

Se você quiser no futuro atualizações a cada 1–2 segundos, o melhor caminho será outro: instalar um firmware próprio que receba os valores por HTTP/MQTT e desenhe diretamente na RAM da tela, sem salvar uma nova imagem na flash a cada atualização.

---

# 11. Restaurar o relógio original

Este projeto não substitui o firmware.

Para voltar imediatamente para o relógio:

```powershell
python src\pc_monitor.py --stock
```

O script apenas troca o tema de volta.

Se necessário, abra a própria interface web do GeekMagic e escolha o tema original.

As imagens criadas pelo projeto começam com:

```text
pcmon_
```

Você pode apagá-las:

```powershell
python src\pc_monitor.py --clean
```

---

# 12. Backup simples das configurações

Antes do primeiro uso, você pode guardar os arquivos JSON acessíveis pelo firmware:

```powershell
python src\backup_device.py 192.168.1.42
```

Será criada uma pasta:

```text
backup_YYYYMMDD_HHMMSS/
```

Esse backup inclui configurações acessíveis pela rede e lista de imagens.

**Não é um dump da flash e não copia o firmware binário.**

Para um dump byte a byte seria necessário acesso UART físico, e isso está fora do objetivo deste projeto.

---

# 13. Inicialização automática com o Windows

Depois de testar tudo, você pode iniciar o monitor automaticamente.

Crie um atalho para:

```text
run_monitor.bat
```

e coloque em:

```text
shell:startup
```

Pressione:

```text
Win + R
```

digite:

```text
shell:startup
```

e coloque o atalho nessa pasta.

---

# 14. Estrutura do projeto

```text
geekmagic_pc_monitor/
│
├── README.md
├── requirements.txt
├── config.example.json
├── run_monitor.bat
│
└── src/
    ├── pc_monitor.py
    └── backup_device.py
```

---

# 15. Próximas evoluções

Depois da primeira versão funcionando, dá para adicionar páginas como:

```text
[1] SISTEMA
CPU / RAM / TEMP

[2] REDE
PING / IP / RX / TX

[3] BATERIA
CARGA / STATUS / TEMPO

[4] GAIA
telemetria de robótica via MQTT/HTTP

[5] SERVIÇOS
status de servidor / GitHub / Home Assistant
```

Também dá para alternar telas automaticamente, mas lembre que no firmware stock cada nova imagem normalmente envolve escrita em flash.

Para dashboards realmente fluidos, a próxima etapa técnica seria firmware customizado via OTA — ainda sem alterar o hardware — mas **não é necessário para este primeiro projeto**.

---

# Referências técnicas

O modelo fotografado é compatível com a família SmallTV Ultra baseada em ESP8266/ESP-12F e display IPS ST7789 de 240×240.

Projetos/comunidades úteis:

- Firmware oficial GeekMagic SmallTV Ultra:  
  https://github.com/GeekMagicClock/smalltv-ultra

- Projeto que documenta o uso da API de imagens sem trocar o firmware:  
  https://github.com/MacheteFlow/GeekMagic-AI-Status

- ESPHome para GeekMagic SmallTV:  
  https://github.com/ViToni/esphome-geekmagic-smalltv

- Firmware comunitário para estudo futuro:  
  https://github.com/iodn/geekmagic-tv-esp8266

---

# Observação

O projeto acessa somente o SmallTV da sua própria rede local.

Ele não abre portas no roteador e não precisa expor o dispositivo à Internet.

Para esse uso, mantenha o SmallTV e o PC na sua rede doméstica e **não faça port-forward da interface web do ESP8266**.

---

# 16. Dual boot — Windows + Ubuntu 24.04

A partir desta versão, o mesmo `pc_monitor.py` detecta automaticamente o sistema operacional.

```text
Windows
  └─ psutil
  └─ LibreHardwareMonitor/WMI (opcional, recomendado para temperaturas/GPU)

Ubuntu 24.04 / Linux
  └─ psutil + /sys/class/thermal
  └─ hwmon / sysfs
  └─ nvidia-smi, se houver GPU NVIDIA
  └─ /sys/class/drm, quando a GPU expõe telemetria por DRM/hwmon
```

Você **não precisa alterar o firmware do SmallTV ao trocar de sistema no dual boot**.
O relógio recebe a mesma imagem 240×240 pela rede; quem coleta os dados é o sistema que estiver em execução.

## Ubuntu 24.04 — instalação rápida

Na pasta do projeto:

```bash
chmod +x install_ubuntu.sh run_monitor.sh
./install_ubuntu.sh
```

O instalador configura:

```text
python3
python3-venv
pip
lm-sensors
ping
ambiente virtual .venv
dependências Python
```

Depois edite:

```bash
nano config.json
```

e informe:

```json
"device_host": "IP_DO_SMALLTV"
```

Teste:

```bash
./run_monitor.sh --test
```

ou diretamente:

```bash
.venv/bin/python src/pc_monitor.py --test
```

Gere uma prévia:

```bash
.venv/bin/python src/pc_monitor.py --preview
```

Execute:

```bash
./run_monitor.sh
```

## Sensores no Ubuntu

Para conferir o que o kernel está detectando:

```bash
sensors
```

Para listar zonas térmicas:

```bash
cat /sys/class/thermal/thermal_zone*/temp
```

Em Ryzen, é comum aparecer `k10temp`; em Intel, `coretemp`.

### NVIDIA

Se o driver proprietário estiver instalado:

```bash
nvidia-smi
```

O script detecta `nvidia-smi` automaticamente e utiliza:

- utilização da GPU;
- temperatura da GPU.

### AMD

Em muitas GPUs AMD, o kernel expõe:

```text
/sys/class/drm/card*/device/gpu_busy_percent
/sys/class/drm/card*/device/hwmon/
```

O script procura esses caminhos automaticamente.

### Intel

Temperatura da CPU costuma ser encontrada normalmente via `coretemp`.
Telemetria de utilização da iGPU Intel varia conforme o driver/kernel; se ela não estiver disponível, o monitor simplesmente omite o uso da GPU.

## Windows

Continua funcionando como antes.

Para ter temperaturas e GPU com maior confiabilidade, abra o **LibreHardwareMonitor** como administrador antes de iniciar o monitor.

O script tenta acessar:

```text
root\LibreHardwareMonitor
```

Se o LibreHardwareMonitor não estiver aberto, CPU/RAM/ping/bateria/rede continuam funcionando.

## Identificação visual

No topo do display aparecerá automaticamente algo como:

```text
PC MONITOR
UBUNTU 24.04
```

ou:

```text
PC MONITOR
WIN 11
```

Isso pode ser desligado em `config.json`:

```json
"show_os_label": false
```

## Configuração relevante

```json
{
  "enable_librehardwaremonitor": true,
  "enable_linux_hwmon": true,
  "enable_nvidia_smi": true,
  "show_os_label": true
}
```



---

# 17. Troca automática: Relógio ↔ Desempenho

O monitor agora possui uma máquina de estados automática.

```text
PC em repouso
    ↓
SmallTV mostra o relógio/clima original
    ↓
CPU sobe / GPU sobe / app configurado é aberto
    ↓
aguarda alguns segundos para evitar falso positivo
    ↓
TELA DE DESEMPENHO
    ↓
CPU/GPU voltam a ficar baixas e os apps fecham
    ↓
aguarda o tempo de cooldown
    ↓
volta para RELÓGIO
```

Configuração padrão:

```json
{
  "auto_performance_mode": true,

  "performance_cpu_enter_percent": 35,
  "performance_gpu_enter_percent": 20,

  "performance_cpu_exit_percent": 20,
  "performance_gpu_exit_percent": 10,

  "performance_enter_hold_seconds": 6,
  "performance_exit_cooldown_seconds": 60,

  "performance_processes": [
    "Inventor.exe",
    "InventorServerHost.exe"
  ]
}
```

## Como funciona

O modo **Desempenho** entra quando qualquer uma destas condições permanece ativa:

- CPU acima de `performance_cpu_enter_percent`;
- GPU acima de `performance_gpu_enter_percent`, se houver telemetria;
- um processo listado em `performance_processes` estiver aberto.

O parâmetro:

```json
"performance_enter_hold_seconds": 6
```

evita mudar de tela só porque a CPU teve um pico de 1 segundo.

Para voltar ao relógio, a máquina precisa ficar abaixo dos limites de saída e sem os processos configurados durante:

```json
"performance_exit_cooldown_seconds": 60
```

Isso evita ficar alternando de tela durante loading screens ou pequenas pausas em jogos.

## Adicionar jogos ou programas

No Windows, abra o Gerenciador de Tarefas → **Detalhes** e veja o nome do executável.

Depois acrescente no `config.json`, por exemplo:

```json
"performance_processes": [
  "Inventor.exe",
  "InventorServerHost.exe",
  "cs2.exe",
  "blender.exe"
]
```

Não é obrigatório cadastrar todos os jogos: se a GPU estiver sendo medida,
o limite de uso da GPU normalmente já ativa a tela de desempenho.

## Observação sobre a flash

A troca de `theme=1` (relógio) para `theme=3` (foto) não é o principal problema.
O desgaste vem de enviar JPEGs novos repetidamente para a flash.

Por isso o projeto continua:

- atualizando o dashboard no máximo no intervalo configurado;
- reutilizando frames já enviados;
- arredondando pequenas oscilações;
- limitando o cache de imagens.

Para o firmware stock, mantenha `push_interval_seconds` em cerca de 60 segundos.


---

# 18. Detecção ampla de aplicativos pesados + retorno rápido

Esta versão foi ajustada para um PC com hardware na faixa de **Ryzen 7 + RTX 3050 + 16 GB RAM**.

A tela de desempenho agora pode entrar por dois caminhos:

```text
1) Aplicativo conhecido de CAD/3D/slicer/render
   OU
2) Carga real do computador:
      CPU >= 20%
      GPU >= 12%
```

Isso cobre também jogos que não estão cadastrados pelo nome.

Exemplos já reconhecidos diretamente incluem:

- Autodesk Inventor
- Fusion 360
- Cura
- Blender
- FreeCAD
- SolidWorks
- AutoCAD
- Revit
- 3ds Max
- Maya
- KeyShot
- PrusaSlicer
- OrcaSlicer
- Bambu Studio
- SuperSlicer
- DaVinci Resolve
- Premiere Pro
- After Effects
- Unreal Editor
- Unity
- Godot

Jogos não precisam estar na lista se gerarem uso de GPU/CPU suficiente.

## RTX 3050 no Windows

Além do LibreHardwareMonitor, o programa agora tenta:

```text
nvidia-smi
```

como fallback.

Assim, com o driver NVIDIA instalado, o uso/temperatura da RTX 3050 pode ser detectado mesmo quando o LibreHardwareMonitor não estiver aberto.

Teste no PowerShell:

```powershell
nvidia-smi
```

Se aparecer a RTX 3050, a detecção de GPU está disponível.

## Tempos novos

Entrada:

```json
"performance_enter_hold_seconds": 4
```

Saída:

```json
"performance_exit_cooldown_seconds": 12
```

Portanto, depois de fechar Inventor/Cura/Fusion/jogo e a carga baixar,
o relógio volta aproximadamente **12 segundos depois**, em vez de esperar um minuto.

A histerese usada é:

```text
ENTRA:
CPU >= 20% ou GPU >= 12% ou app pesado aberto

SAI:
CPU <= 8% e GPU <= 5% e nenhum app pesado aberto
por 12 segundos
```

Isso evita tanto demora excessiva quanto ficar piscando de uma tela para outra.
