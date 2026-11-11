# Inventário de hardware

A aba **Desempenho → Hardware** recolhe informação quando é aberta pela primeira vez. A recolha corre num worker, sem bloquear a janela e sem entrar no ciclo periódico de processos. **Atualizar hardware** força uma nova consulta; chamadas normais reutilizam o inventário durante dez minutos. O instante original e a idade dos dados permanecem visíveis e constam do JSON.

A tabela agrupa componentes e apresenta nome, valor e origem. Valores longos quebram em várias linhas, têm tooltip e podem ser consultados redimensionando as colunas. As notas de interpretação ficam num painel recolhível. O inventário é pontual: bateria, frequência e estado de rede podem mudar antes da próxima atualização.

## Fontes e limites

| Componente | Windows | Linux | Limitação |
|---|---|---|---|
| CPU | psutil; `Win32_Processor`; registo como alternativa para modelo | psutil; `/proc/cpuinfo` | Frequência é a reportada pelo SO, não uma medição de potência. |
| RAM e swap | psutil; módulos em `Win32_PhysicalMemory` | psutil | RAM utilizável pode ser inferior à soma dos módulos; módulos DIMM não são inferidos no Linux. `ConfiguredClockSpeed` usa MHz segundo o contrato CIM; não é convertido implicitamente em MT/s. |
| GPU | Modelo e versão do controlador em `Win32_VideoController`; configurações de adaptadores na classe Display do registo como alternativa | Identificação PCI/controlador em sysfs DRM; VRAM se `mem_info_vram_total` existir | Descobrir uma GPU não fornece utilização, potência nem temperatura. `AdapterRAM` Windows é `uint32` e não confirma a VRAM real; o campo é apresentado como indisponível. Entradas do registo podem ser antigas ou virtuais e não confirmam presença atual. |
| Placa principal / firmware | `Win32_BaseBoard` e `Win32_BIOS`; alternativa no registo `HARDWARE/DESCRIPTION/System/BIOS` | DMI em sysfs | Falta de acesso mantém o campo indisponível; não se pedem privilégios de administrador. |
| Discos | `Win32_DiskDrive`; tipo e barramento em `MSFT_PhysicalDisk` | sysfs block; capacidade calculada de setores de 512 B | HDD/SSD/NVMe só são indicados quando o fornecedor os identifica. Um dispositivo não rotativo do kernel não é automaticamente chamado SSD. |
| Volumes | psutil | psutil | Capacidade livre/total de volumes locais fixos. Não se consulta capacidade de partilhas de rede ou suportes removíveis, para evitar esperas e ativação de dispositivos. |
| Rede | psutil | psutil | Estado e velocidade nominal da ligação, não utilização. IP e MAC não são apresentados nem exportados. |
| Bateria e temperaturas | psutil quando suportado | psutil quando suportado | Ausência de sensor fica explícita. Não há valores simulados neste inventário. |

No Windows é executado **um único subprocesso PowerShell**, sem perfil, sem shell intermediária, sem janela e com limite global de oito segundos. As classes CIM são consultadas em lote; uma classe inacessível não invalida as restantes. Timeout ou resposta inválida preservam a informação portátil e acrescentam uma nota. Não se usa `wmic` e não se instalam drivers ou ferramentas externas.

O resultado, incluindo eventuais indisponibilidades, fica em cache. Isso evita repetir consultas caras quando o fornecedor falha. A opção Atualizar ignora a cache. A cache é protegida contra consultas concorrentes e o chamador recebe uma cópia, evitando alterações acidentais ao resultado partilhado. Cancelar uma recolha não substitui a cache anterior; a consulta externa já em curso pode demorar até ao timeout.

Não são recolhidos números de série, UUID do equipamento, endereços MAC nem IP. O JSON/CSV ainda descreve modelos, nomes de volumes e interfaces do computador; deve ser revisto antes de publicação.

## API e exportação

```python
from expecto_process_manager.core.hardware import detect_hardware, get_cached_hardware

inventory = detect_hardware()                # consulta ou cache
fresh = detect_hardware(refresh=True)        # força nova consulta
print(fresh.collected_at, fresh.age_s)
payload = fresh.as_dict()                    # compatível com JSON
known = get_cached_hardware()                # sem consulta nem espera; pode ser None
for item in fresh.items:
    print(item.category, item.name, item.value, item.source)
```

Chamar `detect_hardware` num worker ou serviço. O módulo de deteção não importa Qt e não modifica processos. A interface usa o gestor de tarefas existente. CSV e JSON são escritos primeiro num ficheiro temporário ao lado do destino e publicados por substituição atómica, mantendo o ficheiro anterior em caso de erro ou cancelamento. CSV inclui notas e origem em linhas próprias; JSON mantém listas `items` e `notes`, `collected_at`, `age_s` e `cache_seconds`.

`get_cached_hardware()` serve para metadados de relatórios: não executa consultas nem espera pelo lock de uma recolha em curso. Devolve a última cópia disponível, mesmo se antiga, com a idade original; devolve `None` quando a cache está vazia ou ocupada. Assim, gerar um relatório nunca desencadeia uma consulta CIM nem perturba a simulação ou medições de desempenho.

## Validação

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_hardware.py -q
```

Os testes usam consultas CIM, dispositivos e sensores simulados: lote único/timeout/JSON inválido, campos ausentes, recusa de acesso, cache/refresh/expiração/cancelamento, VRAM potencialmente truncada, unidades sysfs, proteção de endereços, volumes remotos, exportação atómica e carregamento preguiçoso da página. Uma execução real Windows é registada em `data/hardware-detected.json`; é uma observação deste equipamento, não uma prova de compatibilidade com todos os controladores. A deteção Linux tem validação com fixtures; não foi executada num computador Linux nesta sessão.

Na observação Windows de 10/11/2026, as oito classes CIM devolveram `PermissionDenied`. As alternativas de leitura do registo e psutil permitiram recolher 30 campos, incluindo CPU Intel Core i5-12500H, contagem de núcleos, RAM utilizável, dois adaptadores configurados (NVIDIA RTX 3050 Ti Laptop e Intel UHD), versões de controladores, placa HP 8A26 e firmware AMI F.14. A capacidade de VRAM e sensores não acessíveis permaneceram indisponíveis. A recolha demorou cerca de 1 803 ms e a chamada seguinte à cache cerca de 0,54 ms, numa única observação local; estes tempos não constituem um benchmark comparativo. A prévia `data/hardware-preview.png` foi gerada a partir do JSON, sem repetir consultas.

## Referências dos contratos

- Microsoft: [Win32_PhysicalMemory](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-physicalmemory), propriedade `ConfiguredClockSpeed`, em MHz.
- Microsoft: [Win32_VideoController](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-videocontroller), propriedade `AdapterRAM`, `uint32` em bytes. A impossibilidade de representar capacidades iguais ou superiores a 2³² B é uma consequência desse tipo; o inventário não corrige esse valor por adivinhação.
