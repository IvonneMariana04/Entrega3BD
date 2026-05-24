from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Para Render se usa variable de entorno MONGO_URI
#client = MongoClient("mongodb://ISIS2304F09202610:Bem4bmKESQKU@157.253.236.88:8087")
client = MongoClient(os.environ["MONGO_URI"])

# Base de datos
db = client["ISIS2304F09202610"]

# Colección
resenas = db["Resenas"]


# -----------------------------
# Funciones auxiliares
# -----------------------------

def convertir_id(documento):
    """
    Convierte el ObjectId de MongoDB a string para que APEX pueda leerlo.
    """
    documento["_id"] = str(documento["_id"])
    return documento


def convertir_lista(documentos):
    """
    Convierte una lista de documentos MongoDB en una lista entendible por JSON.
    """
    return [convertir_id(doc) for doc in documentos]


# -----------------------------
# Ruta de prueba
# -----------------------------

@app.get("/")
def inicio():
    return {"estado": "API de reseñas funcionando correctamente"}


# -----------------------------
# RF1 - Crear reseña
# -----------------------------

@app.post("/resenas")
def crear_resena(datos: dict):
    """
    Crea una reseña nueva.
    OJO: la validación de que la reserva esté completada se debe hacer
    desde APEX/Oracle o luego desde una conexión adicional a Oracle.
    """

    # Evita que una reserva tenga más de una reseña
    existe = resenas.find_one({"id_reserva": datos.get("id_reserva")})

    if existe:
        raise HTTPException(
            status_code=400,
            detail="Esta reserva ya tiene una reseña registrada"
        )

    datos["fecha_creacion"] = datetime.now()
    datos["estado"] = "publicada"
    datos["destacada"] = False

    if "votos_utiles" not in datos:
        datos["votos_utiles"] = []

    datos["cantidad_utiles"] = len(datos["votos_utiles"])

    resultado = resenas.insert_one(datos)

    return {
        "mensaje": "Reseña creada correctamente",
        "id_resena": str(resultado.inserted_id)
    }


# -----------------------------
# RF4 - Consultar reseñas de un hotel
# -----------------------------

@app.get("/hoteles/{id_hotel}/resenas")
def consultar_resenas_hotel(id_hotel: int, orden: str = "fecha"):
    """
    Consulta las reseñas publicadas de un hotel.
    Puede ordenar por fecha o por utilidad.
    """

    filtro = {
        "hotel.id_hotel": id_hotel,
        "estado": "publicada"
    }

    if orden == "utilidad":
        ordenamiento = [("destacada", -1), ("cantidad_utiles", -1)]
    else:
        ordenamiento = [("destacada", -1), ("fecha_creacion", -1)]

    documentos = resenas.find(filtro).sort(ordenamiento)

    return convertir_lista(list(documentos))


# -----------------------------
# RF2 - Editar reseña
# -----------------------------

@app.put("/resenas/{id_resena}")
def editar_resena(id_resena: str, datos: dict):
    """
    Edita el comentario y/o la calificación de una reseña.
    """

    cambios = {}

    if "comentario" in datos:
        cambios["comentario"] = datos["comentario"]

    if "calificacion" in datos:
        cambios["calificacion"] = datos["calificacion"]

    cambios["fecha_actualizacion"] = datetime.now()

    resultado = resenas.update_one(
        {"_id": ObjectId(id_resena)},
        {"$set": cambios}
    )

    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")

    return {"mensaje": "Reseña editada correctamente"}


# -----------------------------
# RF3 y RF8 - Eliminar reseña
# -----------------------------

@app.patch("/resenas/{id_resena}/eliminar")
def eliminar_resena(id_resena: str):
    """
    Eliminación lógica de una reseña.
    No borra el documento, solo cambia el estado.
    Sirve para cliente y administrador.
    """

    resultado = resenas.update_one(
        {"_id": ObjectId(id_resena)},
        {
            "$set": {
                "estado": "eliminada",
                "fecha_actualizacion": datetime.now(),
                "destacada": False
            }
        }
    )

    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")

    return {"mensaje": "Reseña eliminada correctamente"}


# -----------------------------
# RF5 - Marcar reseña como útil
# -----------------------------

@app.patch("/resenas/{id_resena}/util")
def marcar_util(id_resena: str, datos: dict):
    """
    Marca una reseña como útil.
    Espera recibir id_usuario.
    """

    id_usuario = datos.get("id_usuario")

    if id_usuario is None:
        raise HTTPException(status_code=400, detail="Debe enviar id_usuario")

    # addToSet evita que el mismo usuario quede repetido
    resultado = resenas.update_one(
        {"_id": ObjectId(id_resena)},
        {"$addToSet": {"votos_utiles": id_usuario}}
    )

    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")

    documento = resenas.find_one({"_id": ObjectId(id_resena)})

    cantidad = len(documento.get("votos_utiles", []))

    resenas.update_one(
        {"_id": ObjectId(id_resena)},
        {"$set": {"cantidad_utiles": cantidad}}
    )

    return {"mensaje": "Voto útil registrado correctamente"}


# -----------------------------
# RF6 - Consultar historial de reseñas propias
# -----------------------------

@app.get("/clientes/{id_cliente}/resenas")
def consultar_resenas_cliente(id_cliente: int, orden: str = "fecha"):
    """
    Consulta todas las reseñas escritas por un cliente.
    """

    filtro = {"id_cliente": id_cliente}

    if orden == "hotel":
        ordenamiento = [("hotel.nombre_hotel", 1)]
    else:
        ordenamiento = [("fecha_creacion", -1)]

    documentos = resenas.find(filtro).sort(ordenamiento)

    return convertir_lista(list(documentos))


# -----------------------------
# RF7 - Responder reseña
# -----------------------------

@app.patch("/resenas/{id_resena}/respuesta")
def responder_resena(id_resena: str, datos: dict):
    """
    Agrega o edita la respuesta oficial del administrador.
    Espera id_admin y texto.
    """

    if "id_admin" not in datos or "texto" not in datos:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar id_admin y texto"
        )

    respuesta = {
        "id_admin": datos["id_admin"],
        "texto": datos["texto"],
        "fecha_respuesta": datetime.now()
    }

    resultado = resenas.update_one(
        {"_id": ObjectId(id_resena)},
        {"$set": {"respuesta_admin": respuesta}}
    )

    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")

    return {"mensaje": "Respuesta del administrador guardada correctamente"}


# -----------------------------
# RF9 - Destacar reseña
# -----------------------------

@app.patch("/resenas/{id_resena}/destacar")
def destacar_resena(id_resena: str):
    """
    Marca una reseña como destacada.
    Primero quita la destacada anterior del mismo hotel.
    """

    documento = resenas.find_one({"_id": ObjectId(id_resena)})

    if documento is None:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")

    id_hotel = documento["hotel"]["id_hotel"]

    # Quitar cualquier destacada anterior de ese hotel
    resenas.update_many(
        {"hotel.id_hotel": id_hotel},
        {"$set": {"destacada": False}}
    )

    # Marcar esta como destacada
    resenas.update_one(
        {"_id": ObjectId(id_resena)},
        {"$set": {"destacada": True}}
    )

    return {"mensaje": "Reseña destacada correctamente"}


# -----------------------------
# RFC1 - Top 10 hoteles por calificación
# -----------------------------

@app.get("/reportes/top-hoteles")
def top_hoteles(fecha_inicio: str, fecha_fin: str):
    """
    Consulta los 10 hoteles con mejor calificación promedio
    en un período definido.
    Formato de fecha esperado: YYYY-MM-DD
    """

    inicio = datetime.fromisoformat(fecha_inicio)
    fin = datetime.fromisoformat(fecha_fin)

    pipeline = [
        {
            "$match": {
                "estado": "publicada",
                "fecha_creacion": {
                    "$gte": inicio,
                    "$lte": fin
                }
            }
        },
        {
            "$group": {
                "_id": {
                    "id_hotel": "$hotel.id_hotel",
                    "nombre_hotel": "$hotel.nombre_hotel",
                    "ciudad": "$hotel.ciudad.nombre_ciudad"
                },
                "calificacion_promedio": {"$avg": "$calificacion"},
                "total_resenas": {"$sum": 1}
            }
        },
        {
            "$sort": {
                "calificacion_promedio": -1,
                "total_resenas": -1,
                "_id.id_hotel": 1
            }
        },
        {
            "$limit": 10
        },
        {
            "$project": {
                "_id": 0,
                "id_hotel": "$_id.id_hotel",
                "nombre_hotel": "$_id.nombre_hotel",
                "ciudad": "$_id.ciudad",
                "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
                "total_resenas": 1
            }
        }
    ]

    return list(resenas.aggregate(pipeline))


# -----------------------------
# RFC2 - Evolución reputación hotel
# -----------------------------

@app.get("/reportes/evolucion/{id_hotel}")
def evolucion_reputacion(id_hotel: int, anio: int):
    """
    Muestra la calificación promedio mes a mes de un hotel
    durante un año determinado.
    """

    inicio = datetime(anio, 1, 1)
    fin = datetime(anio + 1, 1, 1)

    pipeline = [
        {
            "$match": {
                "hotel.id_hotel": id_hotel,
                "estado": "publicada",
                "fecha_creacion": {
                    "$gte": inicio,
                    "$lt": fin
                }
            }
        },
        {
            "$group": {
                "_id": {"mes": {"$month": "$fecha_creacion"}},
                "calificacion_promedio": {"$avg": "$calificacion"},
                "total_resenas": {"$sum": 1}
            }
        },
        {
            "$sort": {"_id.mes": 1}
        },
        {
            "$project": {
                "_id": 0,
                "mes": "$_id.mes",
                "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
                "total_resenas": 1
            }
        }
    ]

    return list(resenas.aggregate(pipeline))


# -----------------------------
# RFC3 - Comparativo hoteles por ciudad
# -----------------------------

@app.get("/reportes/comparativo-ciudad/{ciudad}")
def comparativo_ciudad(ciudad: str):
    """
    Compara los hoteles de una ciudad:
    promedio, total de reseñas, porcentaje con respuesta,
    porcentaje destacadas y si están debajo del promedio de la ciudad.
    """

    pipeline = [
        {
            "$match": {
                "hotel.ciudad.nombre_ciudad": ciudad,
                "estado": "publicada"
            }
        },
        {
            "$group": {
                "_id": {
                    "id_hotel": "$hotel.id_hotel",
                    "nombre_hotel": "$hotel.nombre_hotel"
                },
                "calificacion_promedio": {"$avg": "$calificacion"},
                "total_resenas": {"$sum": 1},
                "resenas_con_respuesta": {
                    "$sum": {
                        "$cond": [
                            {"$ifNull": ["$respuesta_admin", False]},
                            1,
                            0
                        ]
                    }
                },
                "resenas_destacadas": {
                    "$sum": {
                        "$cond": ["$destacada", 1, 0]
                    }
                }
            }
        },
        {
            "$setWindowFields": {
                "output": {
                    "promedio_ciudad": {
                        "$avg": "$calificacion_promedio"
                    }
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "id_hotel": "$_id.id_hotel",
                "nombre_hotel": "$_id.nombre_hotel",
                "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
                "total_resenas": 1,
                "porcentaje_con_respuesta": {
                    "$round": [
                        {
                            "$multiply": [
                                {"$divide": ["$resenas_con_respuesta", "$total_resenas"]},
                                100
                            ]
                        },
                        2
                    ]
                },
                "porcentaje_destacadas": {
                    "$round": [
                        {
                            "$multiply": [
                                {"$divide": ["$resenas_destacadas", "$total_resenas"]},
                                100
                            ]
                        },
                        2
                    ]
                },
                "promedio_ciudad": {"$round": ["$promedio_ciudad", 2]},
                "debajo_promedio_ciudad": {
                    "$lt": ["$calificacion_promedio", "$promedio_ciudad"]
                }
            }
        },
        {
            "$sort": {
                "calificacion_promedio": 1
            }
        }
    ]

    return list(resenas.aggregate(pipeline))