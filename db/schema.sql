CREATE TYPE ambito AS ENUM (
    'MAYORES',
    'DISCAPACIDAD',
    'SALUD_MENTAL',
    'INFANCIA_Y_JUVENTUD',
    'MUJER',
    'MIGRACION',
    'INCLUSION_SOCIAL',
    'EDUCACION_Y_FORMACION',
    'EMPLEO_E_INSERCION_LABORAL',
    'SALUD_Y_ATENCION_SOCIOSANITARIA',
    'VOLUNTARIADO_Y_PARTICIPACION_COMUNITARIA',
    'CULTURA_Y_DESARROLLO_COMUNITARIO'
);

CREATE TABLE provincia (
    codigo CHAR(2) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL
);

CREATE TABLE localidad (
    codigo INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    codigo_provincia CHAR(2) NOT NULL REFERENCES provincia (codigo),
    UNIQUE (nombre, codigo_provincia)
);

CREATE TABLE entidad (
    cod_entidad INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(300) NOT NULL,
    ambito ambito NOT NULL,
    direccion VARCHAR(300),
    codigo_postal CHAR(5),
    longitud DOUBLE PRECISION CHECK (longitud BETWEEN -180 AND 180),
    latitud DOUBLE PRECISION CHECK (latitud BETWEEN -90 AND 90),
    descripcion TEXT,
    contacto VARCHAR(300),
    url VARCHAR(500),
    codigo_localidad INTEGER NOT NULL REFERENCES localidad (codigo),
    CHECK (codigo_postal IS NULL OR codigo_postal ~ '^[0-9]{5}$')
);

CREATE INDEX idx_entidad_coordenadas ON entidad (longitud, latitud);
CREATE INDEX idx_entidad_localidad ON entidad (codigo_localidad);
CREATE INDEX idx_entidad_ambito ON entidad (ambito);
CREATE INDEX idx_entidad_codigo_postal ON entidad (codigo_postal);
CREATE INDEX idx_localidad_provincia ON localidad (codigo_provincia);
