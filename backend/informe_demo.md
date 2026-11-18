# Informe de Carga al Almacén PostgreSQL (ONGD)

## 1. Estado de la Base de Datos
- **Inicial**: 0 provincias, 0 localidades, 0 entidades
- **Final**: 3 provincias, 9 localidades, 9 entidades

## 2. Resumen por Fuente
| Fuente | Válidas extraídas | Insertadas BD | Omitidas dup. BD | Errores | Reparaciones |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `CV` | 9 | 9 | 0 | 3 | 3 |

### Detalle `CV`
- **Errores por tipo**: `duplicado`: 2, `semantico`: 1
- **Errores detectados**:
  - [fila 7] `id` (`duplicado`): Identificador duplicado en origen: '1491'
  - [fila 9] `provincia` (`semantico`): Inconsistencia entre cod_ine_mun ('03063') y provincia ('València/Valencia')
  - [fila 12] `id` (`duplicado`): Identificador duplicado en origen: '911'
- **Reparaciones aplicadas (3)**:
  - [fila 3] `y_25830`: `4333847,00` -> `4333847.00` (Reemplazo de coma decimal por punto)
  - [fila 10] `coordenadas`: `x=9999999, y=9999999` -> `lat=38.370194, lon=-0.476713` (Coordenadas obtenidas mediante geocodificación de la dirección)
  - [fila 11] `coordenadas`: `x=715185, y=None` -> `x=715185.0, y=4369513.0` (Coordenadas UTM recuperadas desde el campo WKT)

## 3. Contenido Almacenado en PostgreSQL
### Distribución por ámbito
- `DISCAPACIDAD`: 2
- `INCLUSION_SOCIAL`: 2
- `MAYORES`: 4
- `SALUD_MENTAL`: 1

### Entidades en `entidad`
| ID | Nombre | Ámbito | Localidad (Prov) | CP | Coordenadas |
| ---: | :--- | :--- | :--- | :--- | :--- |
| 1 | Accem - V.T. colect. desfavorecidos Cuenca | `INCLUSION_SOCIAL` | València (46) | 46007 | 39.462275, -0.389809 |
| 2 | CLUB DE CONVIVENCIA DE TERCERA EDAD BICORP | `MAYORES` | Bicorp (46) | 46825 | 39.132806, -0.786718 |
| 3 | CLUB DE CONVIVENCIA (FUNDACION SINDROME DE DOWN) | `DISCAPACIDAD` | Castelló de la Plana (12) | 12006 | 39.987326, -0.060437 |
| 4 | Centro ocupacional para personas con diversidad funcional AYORA | `DISCAPACIDAD` | Ayora (46) | 46620 | 39.059046, -1.058960 |
| 5 | CEEM CENTRO TERAPEUTICO MASÍA DE PAVÍA | `SALUD_MENTAL` | Turís (46) | 46192 | 39.394438, -0.591864 |
| 6 | RESIDENCIA PARA PERSONAS MAYORES DEPENDIENTES BALLESOL COSTA BLANCA | `MAYORES` | la Vila Joiosa/Villajoyosa (03) | 03570 | 38.523790, -0.170292 |
| 7 | RESIDENCIA PARA PERSONAS MAYORES DEPENDIENTES GERIATRICO DONYA ROSA | `MAYORES` | Alacant/Alicante (03) | 03015 | 38.370194, -0.476713 |
| 8 | Ciudad de la Esperanza (Residencia A) | `INCLUSION_SOCIAL` | Aldaia (46) | 46909 | 39.448312, -0.499244 |
| 9 | CLUB DE CONVIVENCIA TERCERA EDAD DE EL PERELLO | `MAYORES` | Sueca (46) | 46420 | 39.277776, -0.277514 |
