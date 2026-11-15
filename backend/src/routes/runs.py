from fastapi import APIRouter,Depends,Response
from src.config.database import get_db
from src.utils.auth import current_user,editor
from src.schemas.run import RunInput
from src.controllers.run_controller import list_runs,create_run,get_run
from src.services.export_service import export_common_weight
router=APIRouter(prefix='/runs')
@router.get('')
def index(db=Depends(get_db),user=Depends(current_user)):return list_runs(db)
@router.post('',status_code=201)
def create(data:RunInput,db=Depends(get_db),user=Depends(editor)):return create_run(db,data)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),user=Depends(current_user)):return get_run(db,id)
@router.get('/{id}/export')
def export(id:int,db=Depends(get_db),user=Depends(current_user)):
    run=get_run(db,id)
    return Response(export_common_weight(run),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="common-weight-rank-{id}.csv"'})
