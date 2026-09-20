from aiogram import Router
from app.handlers.user_handlers import user_router
from app.handlers.payment_handlers import payment_router
from app.handlers.download_handlers import download_router
from app.handlers.admin_handlers import admin_router

main_router = Router()
main_router.include_router(user_router)
main_router.include_router(payment_router)
main_router.include_router(download_router)
main_router.include_router(admin_router)