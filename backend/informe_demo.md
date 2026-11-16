# Informe de Carga al Almacén PostgreSQL (ONGD)

## 1. Estado de la Base de Datos
- **Inicial**: 0 provincias, 0 localidades, 0 entidades
- **Final**: 2 provincias, 7 localidades, 8 entidades

## 2. Resumen por Fuente
| Fuente | Válidas extraídas | Insertadas BD | Omitidas dup. BD | Errores | Reparaciones |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `CAN` | 8 | 8 | 0 | 4 | 21 |

### Detalle `CAN`
- **Errores por tipo**: `duplicado`: 2, `nulo`: 1, `semantico`: 1
- **Errores detectados**:
  - [fila 2] `provincia` (`semantico`): Provincia/municipio inconsistentes o no válidos: prov='38', mun='35030'
  - [fila 6] `nombre` (`nulo`): El campo denominación es nulo o no informado (_U)
  - [fila 9] `numero_registro` (`duplicado`): Entidad duplicada con identificador 'ERE2018CA00001'
  - [fila 12] `numero_registro` (`duplicado`): Entidad duplicada con identificador 'ERE2022TF00012'
- **Reparaciones aplicadas (21)**:
  - [fila 1] `provincia/localidad`: `prov=99:Desconocida, mun=38430:Tacoronte` -> `prov=38:Santa Cruz de Tenerife, loc=Tacoronte` (Deducción de provincia/localidad por código postal/INE o inversión de artículo)
  - [fila 1] `contacto`: `(34)922584030` -> `Tel: 922584030` (Limpieza de prefijo telefónico internacional (34) y unión con ' / ')
  - [fila 1] `codigo_postal`: `None` -> `38359` (Código postal obtenido mediante geocodificación de la dirección)
  - [fila 3] `provincia/localidad`: `prov=38:Santa Cruz de Tenerife, mun=38230:Laguna (La)` -> `prov=38:Santa Cruz de Tenerife, loc=La Laguna` (Deducción de provincia/localidad por código postal/INE o inversión de artículo)
  - [fila 3] `contacto`: `(34)649740957` -> `Tel: 649740957` (Limpieza de prefijo telefónico internacional (34) y unión con ' / ')
  - [fila 3] `codigo_postal`: `None` -> `38207` (Código postal obtenido mediante geocodificación de la dirección)
  - [fila 4] `contacto`: `(34)922433500` -> `Tel: 922433500` (Limpieza de prefijo telefónico internacional (34) y unión con ' / ')
  - [fila 5] `provincia/localidad`: `prov=_U:_U, mun=38060:Arona` -> `prov=38:Santa Cruz de Tenerife, loc=Arona` (Deducción de provincia/localidad por código postal/INE o inversión de artículo)
  - [fila 5] `contacto`: `(34)922169398` -> `Tel: 922169398` (Limpieza de prefijo telefónico internacional (34) y unión con ' / ')
  - [fila 5] `codigo_postal`: `None` -> `38627` (Código postal obtenido mediante geocodificación de la dirección)
  - [fila 7] `provincia/localidad`: `prov=38:Santa Cruz de Tenerife, mun=38250:Matanza de Acentejo (La)` -> `prov=38:Santa Cruz de Tenerife, loc=La Matanza de Acentejo` (Deducción de provincia/localidad por código postal/INE o inversión de artículo)
  - [fila 7] `contacto`: `(34)922496118` -> `Tel: 922496118` (Limpieza de prefijo telefónico internacional (34) y unión con ' / ')
  - [fila 7] `codigo_postal`: `None` -> `38370` (Código postal obtenido mediante geocodificación de la dirección)
  - [fila 8] `provincia/localidad`: `prov=35:Las Palmas, mun=35001:Palmas de Gran Canaria (Las)` -> `prov=35:Las Palmas, loc=Las Palmas de Gran Canaria` (Deducción de provincia/localidad por código postal/INE o inversión de artículo)
  - [fila 8] `contacto`: `(34)928469754` -> `Tel: 928469754` (Limpieza de prefijo telefónico internacional (34) y unión con ' / ')
  - [fila 8] `codigo_postal`: `None` -> `35008` (Código postal obtenido mediante geocodificación de la dirección)
  - [fila 10] `provincia/localidad`: `prov=38:Santa Cruz de Tenerife, mun=38230:Laguna (La)` -> `prov=38:Santa Cruz de Tenerife, loc=La Laguna` (Deducción de provincia/localidad por código postal/INE o inversión de artículo)
  - [fila 10] `contacto`: `(34)637737979` -> `Tel: 637737979` (Limpieza de prefijo telefónico internacional (34) y unión con ' / ')
  - [fila 10] `codigo_postal`: `None` -> `38202` (Código postal obtenido mediante geocodificación de la dirección)
  - [fila 11] `contacto`: `(34)628747191` -> `Tel: 628747191` (Limpieza de prefijo telefónico internacional (34) y unión con ' / ')
  - [fila 11] `codigo_postal`: `None` -> `38007` (Código postal obtenido mediante geocodificación de la dirección)

## 3. Contenido Almacenado en PostgreSQL
### Distribución por ámbito
- `INCLUSION_SOCIAL`: 5
- `MAYORES`: 1
- `SALUD_Y_ATENCION_SOCIOSANITARIA`: 1
- `VOLUNTARIADO_Y_PARTICIPACION_COMUNITARIA`: 1

### Entidades en `entidad`
| ID | Nombre | Ámbito | Localidad (Prov) | CP | Coordenadas |
| ---: | :--- | :--- | :--- | :--- | :--- |
| 1 | Asociacion De Mayores Viñatigos Centenarios | `MAYORES` | Tacoronte (38) | 38359 | 28.461555, -16.413378 |
| 2 | Asociacion Activ@ Drago | `INCLUSION_SOCIAL` | La Laguna (38) | 38207 | 28.478262, -16.308938 |
| 3 | Asociacion Padisbalta | `VOLUNTARIADO_Y_PARTICIPACION_COMUNITARIA` | Breña Alta (38) | - | 28.651299, -17.800712 |
| 4 | Asociación De Senegaleses Diapo | `INCLUSION_SOCIAL` | Arona (38) | 38627 | 28.049948, -16.676908 |
| 5 | Vida Con Salud Asoc Sociaocultural | `SALUD_Y_ATENCION_SOCIOSANITARIA` | La Matanza de Acentejo (38) | 38370 | 28.439977, -16.448427 |
| 6 | Asociacion Centro Europeo De Estudios Sobre Flujos Migratorios | `INCLUSION_SOCIAL` | Las Palmas de Gran Canaria (35) | 35008 | 28.150739, -15.418603 |
| 7 | Asoc Asistencial Nahia | `INCLUSION_SOCIAL` | La Laguna (38) | 38202 | 28.489704, -16.322384 |
| 8 | Asoc Afamca - Tenerife (asociacion De La Familia Canaria) | `INCLUSION_SOCIAL` | Santa Cruz de Tenerife (38) | 38007 | 28.458543, -16.268951 |
