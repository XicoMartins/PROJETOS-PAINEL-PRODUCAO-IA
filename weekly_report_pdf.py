"""Paginated A4 dashboard tables preserving the weekly panel visual language."""
from io import BytesIO
from pathlib import Path
from html import escape
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, Image
from weekly_control import SAO_PAULO, weekly_periods
GRAPHITE=colors.HexColor('#202326'); SOFT=colors.HexColor('#34383d'); WINE=colors.HexColor('#7f1d2d'); TEAL=colors.HexColor('#0f716d')
STYLE=ParagraphStyle('cell',fontName='Helvetica',fontSize=7.5,leading=10,wordWrap='CJK')
BOLD=ParagraphStyle('bold',parent=STYLE,fontName='Helvetica-Bold')
WHITE=ParagraphStyle('white',parent=BOLD,textColor=colors.white)
HEADER=ParagraphStyle('header',parent=WHITE,fontSize=6.3,leading=8)
TITLE=ParagraphStyle('title',parent=WHITE,fontSize=12,leading=16)
CENTER=ParagraphStyle('center',parent=STYLE,alignment=1)
def p(text,style=STYLE): return Paragraph(escape(str(text)).replace('\n','<br/>'),style)
def number(value): return '-' if value is None else str(value)
def instant(value): return value.astimezone(SAO_PAULO).strftime('%d/%m/%Y %H:%M') if value else 'primeira emissão'
def reconciliation(row,field,label):
    before=row['previous']; current=row['current']
    a=before.get(field) if before else '0'; b=current.get(field) if current else '0'
    caption='Saldo anterior + variação = saldo atual' if label=='Saldo' else f'{label} anterior + atualização = total'
    return f'{caption}: {number(a)} + {number(row["deltas"][field])} = {number(b)}'
def logo(brand,width=65):
    image=Image(str(Path(__file__).parent/'assets'/'logos'/f'{brand}.png'))
    ratio=image.imageHeight/image.imageWidth
    image.drawWidth=width; image.drawHeight=width*ratio
    return image

def status(value):
    if value is None: return p('-\nDADOS INCOMPLETOS',CENTER),colors.HexColor('#eeeeee')
    pending=Decimal(value)<0
    style=ParagraphStyle('status',parent=CENTER,fontName='Helvetica-Bold',textColor=colors.white if pending else colors.HexColor('#00512c'))
    return p(f'{value}\n'+('PENDENTE' if pending else 'COBERTO'),style),colors.HexColor('#d9212d' if pending else '#dcefdc')

def summary(snap,side,width):
    rows=[row for row in snap['rows'].values() if row['kind']=='component']
    target=snap['targets'][side]
    quantities=[row['quantity_per_set'] for row in rows]
    components=None if target is None or any(v is None for v in quantities) else Decimal(target)*sum((Decimal(v) for v in quantities),Decimal(0))
    field='previous_balance' if side==0 else 'current_balance'
    pending=[Decimal(row[field]) for row in rows if row[field] is not None and Decimal(row[field])<0]
    cards=Table([[p('COMPONENTES DA META\n'+number(components),CENTER),p('PEÇAS PENDENTES\n'+str(sum((-v for v in pending),Decimal(0))),CENTER),p('REFERÊNCIAS PENDENTES\n'+str(len(pending)),CENTER)]],colWidths=[width/3]*3)
    cards.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f4f4f4')),('BOX',(0,0),(-1,-1),.5,colors.white),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    return cards

def build_pdf(reports,generated_at):
    output=BytesIO(); page=landscape(A4); width=page[0]-40; gap=10; half=(width-gap)/2
    doc=SimpleDocTemplate(output,pagesize=page,leftMargin=20,rightMargin=20,topMargin=20,bottomMargin=30,title='Controle semanal de remessas e retornos')
    story=[]
    for index,report in enumerate(reports):
        if index: story.append(PageBreak())
        snap=report['snapshot']; identity=snap['identity']; general=report['previous_at'] is None; unchanged=report.get('status')=='unchanged'
        heading='SEM ALTERAÇÕES' if unchanged else ('RELATÓRIO GERAL' if general else 'RELATÓRIO DE ATUALIZAÇÃO')
        hero=Table([[p('CONTROLE SEMANAL DE REMESSAS E RETORNOS\n'+heading,TITLE),p(f'{identity["display"]} · Pintura externa\n{identity["cliente"]} · Nº {identity["numero_display"]} · {identity["codigo_pintura"]}',WHITE)]],colWidths=[width*.59,width*.41])
        hero.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),GRAPHITE),('LINEABOVE',(0,0),(-1,0),3,colors.HexColor('#bd1622')),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12),('VALIGN',(0,0),(-1,-1),'TOP')]))
        last_entry=report.get('last_entry_at')
        story.extend([hero,Spacer(1,6),p(f'Emissão: {instant(generated_at)} (America/Sao_Paulo) | Relatório anterior: {instant(report["previous_at"])}'),p('Último lançamento: '+(instant(last_entry) if last_entry else 'não disponível')),Spacer(1,8)])
        if unchanged:
            updated=report.get('source_updated_at')
            story.extend([p('Nenhuma alteração desde o último relatório.',BOLD),Spacer(1,10),p('Última atualização dos dados: '+(instant(updated) if updated else 'não disponível'))])
        heads=[]
        periods=report.get('periods') or weekly_periods(generated_at)
        for side,(label,brand,color) in enumerate((('RETORNO','multipint',WINE),('REMESSA','mtech',TEAL))):
            badge_style=ParagraphStyle('badge',parent=CENTER,fontName='Helvetica-Bold',textColor=color)
            period=periods[side]
            date_label=f'{period.start:%d/%m} - {period.end:%d/%m/%Y}'
            heading=Table([[p(label+'\n'+date_label,BOLD),logo(brand),p('META ACUMULADA\n'+number(snap['targets'][side]),badge_style)]],colWidths=[half*.25,half*.40,half*.35])
            heading.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BACKGROUND',(2,0),(2,0),colors.HexColor('#f3e9eb' if side==0 else '#e1f0ef')),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]));heads.append(heading)
        # A single split-capable grid keeps paired dashboard panels aligned across pages.
        left=[half*.26,half*.07,half*.10,half*.10,half*.09,half*.14,half*.24]
        right=[half*.32,half*.09,half*.13,half*.13,half*.13,half*.20]
        widths=left+[gap]+right
        data=[[heads[0],*['']*6,'',heads[1],*['']*5],[*[p(v,HEADER) for v in ('COMPONENTE','QT/DY','REMESSA','RETORNO','SALDO','A ENVIAR','A RETORNAR')],'',*[p(v,HEADER) for v in ('COMPONENTE','QT/DY','REMESSA','RETORNO','SALDO','A ENVIAR')]]]
        commands=[('SPAN',(0,0),(6,0)),('SPAN',(8,0),(13,0)),('BACKGROUND',(0,0),(-1,-1),colors.white),('LINEABOVE',(0,0),(6,0),4,WINE),('LINEABOVE',(8,0),(13,0),4,TEAL),('BACKGROUND',(0,1),(6,1),SOFT),('BACKGROUND',(8,1),(13,1),SOFT),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,1),(-1,-1),7),('BOTTOMPADDING',(0,1),(-1,-1),7),('GRID',(0,1),(6,-1),.3,colors.HexColor('#d7dadd')),('GRID',(8,1),(13,-1),.3,colors.HexColor('#d7dadd'))]
        for item in report['rows']:
            row=item['current'] or item['previous']; name=row['display_name']+(' (REMOVIDO)' if item['removed'] else '')
            chunks=[name[i:i+240] for i in range(0,len(name),240)] or ['']
            # A source key may be as long as the name; bound the repeated prefix.
            identifier = row['component_key']
            if len(identifier) > 48:
                identifier = identifier[:45] + '...'
            for chunk_index,chunk in enumerate(chunks):
                label=chunk if chunk_index==0 else identifier+' (continuação)\n'+chunk
                values={field:('0' if item['removed'] else row[field]) for field in ('total_remessa','total_retorno','painting_balance','return_remittance_balance','previous_balance','current_balance')}
                send,bg_send=status(values['return_remittance_balance']);ret,bg_ret=status(values['previous_balance']);current,bg_current=status(values['current_balance'])
                n=len(data)
                data.append([p(label,WHITE),p(number(row['quantity_per_set']),CENTER),p(number(values['total_remessa']),CENTER),p(number(values['total_retorno']),CENTER),p(number(values['painting_balance']),CENTER),send,ret,'',p(label,WHITE),p(number(row['quantity_per_set']),CENTER),p(number(values['total_remessa']),CENTER),p(number(values['total_retorno']),CENTER),p(number(values['painting_balance']),CENTER),current])
                for column,color in ((0,SOFT),(8,SOFT),(2,colors.HexColor('#fff0a8')),(10,colors.HexColor('#fff0a8')),(4,colors.HexColor('#dcecf8')),(12,colors.HexColor('#dcecf8')),(5,bg_send),(6,bg_ret),(13,bg_current)):
                    commands.append(('BACKGROUND',(column,n),(column,n),color))
        table=Table(data,colWidths=widths,repeatRows=2,splitByRow=1,splitInRow=0);table.setStyle(TableStyle(commands));story.append(table)
        total_caption='TOTAL DO PROJETO - valores atuais acumulados da base completa.' if unchanged else 'TOTAL DO PROJETO - resumos da base completa, incluindo itens fora desta atualização.'
        story.extend([Spacer(1,8),p(total_caption,BOLD)])
        summaries=Table([[summary(snap,0,half),'',summary(snap,1,half)]],colWidths=[half,gap,half]);summaries.setStyle(TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]));story.append(summaries)
        if not general and not unchanged:
            story.extend([Spacer(1,10),p('RECONCILIAÇÃO DOS ITENS ALTERADOS',BOLD)])
            reconciled=[[p('COMPONENTE',WHITE),p('ANTERIOR + ATUALIZAÇÃO = ACUMULADO ATUAL',WHITE)]]
            for row in report['rows']:
                value=row['current'] or row['previous']
                lines=[reconciliation(row,field,label) for field,label in (('total_remessa','Remessa'),('total_retorno','Retorno'),('painting_balance','Saldo'))]
                if row['removed']: lines.append('Item removido da base atual.')
                elif all(value in ('0',None) for value in row['deltas'].values()): lines.append('Cadastro, meta ou movimentos alterados; acumulados revisados.')
                reconciled.append([p(value['display_name']),p('\n'.join(lines))])
            rec=Table(reconciled,colWidths=[width*.27,width*.73],repeatRows=1,splitInRow=1);rec.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),SOFT),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#d7dadd')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.append(rec)
        story.extend([Spacer(1,8),p('Valores atuais acumulados. Saldo = remessa - retorno. Atualizações líquidas podem ser negativas. Verde: coberto; vermelho: pendente. Dados ausentes são apresentados como -.')])
    def footer(canvas,document):
        canvas.setFillColor(GRAPHITE);canvas.setFont('Helvetica',8);canvas.drawRightString(page[0]-20,16,f'Página {document.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
