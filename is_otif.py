# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import time
import pooler
from osv import fields, osv
from tools.translate import _
import netsvc



class is_otif_cause(osv.osv):
    _name = 'is.otif.cause'
    _description = 'Liste des anomalies'
    _columns = {
        'name': fields.char('Anomalie', size=256, required=True),
        'description': fields.text('Description'),
    }
is_otif_cause()


class is_otif(osv.osv):
    _name = "is.otif"
    _description = "OTIF"

    def set_anomalie(self, cr, uid, ids, vals, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        anomalie=""
        is_anomalie=False
        decaled_order=0
        for obj in self.browse(cr, uid, ids, context=context):
            if obj.final_date:
                if obj.initial_qty != obj.qty_delivered:
                    anomalie="Anomalie Qt"
                if obj.initial_date != obj.final_date:
                    decaled_order=1
                    if anomalie:
                      anomalie=anomalie+", "
                    anomalie=anomalie+"Anomalie date"
                if anomalie:
                    is_anomalie = True
        vals["anomalie"]    = anomalie
        vals["is_anomalie"] = is_anomalie
        vals["decaled_order"] = decaled_order
        return vals


    #Recerche des anomalies à chaque modification dans OTIF (y-compris lors d'une modification manuelle)
    def write(self, cr, uid, ids, vals, context=None):
        res=super(is_otif, self).write(cr, 1, ids, vals, context=context)
        vals=self.set_anomalie(cr, uid, ids, vals, context=context)
        res=super(is_otif, self).write(cr, 1, ids, vals, context=context)
        return res


    _columns = {
        'order_id': fields.many2one('sale.order', 'Order Number', readonly=True),
        'order_line_id': fields.many2one('sale.order.line', 'Order Line', readonly=True),
        'order_date': fields.date('Order Date', readonly=True),
        'order_time': fields.char('Order Time', size=8, readonly=True),
        'partner_id': fields.many2one('res.partner', 'Customer', readonly=True),
        'partner_classification': fields.char('Classification', size=256, readonly=True),
        'company_code': fields.char('Company Code', size=256, readonly=True),
        'product_code': fields.char('Product Code', size=256, readonly=True),
        'product_name': fields.char('Product Name', size=256, readonly=True),
        'produce_delay': fields.float('Production Delay', readonly=True),
        'initial_qty': fields.float('Initial Quantity', readonly=False),
        'qty_delivered': fields.float('Quantity Delivered', readonly=False),
        'initial_date': fields.date('Initial shipping date', readonly=False),
        'final_date': fields.date('Final shipping date', readonly=False),
        'cause_id': fields.many2one('is.otif.cause', 'Cause'),
        'comment': fields.text('Comment'),
        'cost': fields.char('Cost', size=256, readonly=False),
        'waiting_panif': fields.boolean('Attente panif', readonly=True),
        'waiting_panif_date': fields.date(u'Date de levée attente panif', readonly=True),
        'waiting_quality': fields.boolean(u'Attente Qualité', readonly=True),
        'waiting_quality_date': fields.date(u'Date de levée attente Qualité', readonly=True),

        'blocage_total': fields.boolean(u'Blocage Total', readonly=True),
        'date_blocage_total': fields.date(u'Date levée du blocage total', readonly=True),

        'blocage_production': fields.boolean('Blocage Production', readonly=True),
        'date_blocage_prod': fields.date(u'Date levée du blocage production', readonly=True),

        'blocage_exped': fields.boolean(u'Blocage Expédition', readonly=True),
        'date_blocage_exped': fields.date(u'Date levée du blocage', readonly=True),

        'decaled_order': fields.integer('Decaled Order', readonly=True),
        'scind_cmd': fields.integer(u'Commande Scindée', readonly=True),
        'sold_cmd': fields.integer(u'Commande Soldée', readonly=True),
        'production_date': fields.date('Production Date', readonly=True),
        'production_num': fields.char('Production number', size=256, readonly=True),
        'initial_production_date': fields.datetime('Initial production Date', readonly=True),
        'final_production_date': fields.datetime('Finale production date', readonly=True),
        'control': fields.char('Control', size=256, readonly=True),
        'control_delay': fields.float('Control Delay', readonly=True),
        'control_product_date': fields.date(u'Produit contrôlé libéré le', readonly=True),
        'is_anomalie': fields.boolean('Existe Anomalie', readonly=True),
        'anomalie': fields.char('Anomalie', size=256, readonly=True),
    }

    _defaults = {
        'is_anomalie': False,
    }

is_otif()

class sale_order(osv.osv):
    _inherit = 'sale.order'

    _columns = {
        'nb_confirmed': fields.integer('Confirmation number', readonly=True),
    }

    _defaults = {
        'nb_confirmed': 0,
    }

    #Le nouveau champ 'nb_confirmed' permet de savoir si la commande a déjà été validée ou pas
    #-> Il ne faut pas enregistrer une deuxième fois une commande déjà validée même si elle contient d'autres lignes
    def action_wait(self, cr, uid, ids, *args):
        for order in self.browse(cr, uid, ids):
            nb = order.nb_confirmed + 1
            self.write(cr, uid, order.id, {'nb_confirmed': nb})
        res = super(sale_order, self).action_wait(cr, uid, ids, *args)
        return res

sale_order()


class sale_order_line(osv.osv):
    _inherit = 'sale.order.line'

    def is_product_tr(self, cr, uid, code_product, context=None):
        if code_product and code_product[:2] == 'TR':
            return True
        return False

    def is_order_ec(self, cr, uid, order_type, context=None):
        if not order_type:
            return False
        if order_type != 'EC':
            return True
        return False

    def insert_line_into_otif(self, cr, uid, ids, line, context=None):
        """ Insérer les lignes de commandes dans la table is_otif lors de la première validation des lignes de commandes
        """
        otif_obj = self.pool.get('is.otif')
        if not self.is_product_tr(cr, uid, line.product_id.default_code, context): #or self.is_order_ec(cr, uid, line.order_id.sale_oder_type, context):
            #Ne pas prendre en compte les échantillions
            if line.order_id.sale_order_type!="sample":
                vals = {
                    'order_id': line.order_id.id,
                    'order_line_id': line.id,
                    'order_date': line.order_id.date_order,
                    'order_time': time.strftime('%H:%M:%S', (time.strptime(line.order_id.create_date, '%Y-%m-%d %H:%M:%S'))), # A convertir en time
                    'partner_id': line.order_partner_id.id,
                    'partner_classification': line.order_partner_id.classification,
                    'company_code': line.order_id.section_id.code,
                    'product_code': line.product_id.default_code,
                    'product_name': line.product_id.name,
                    'produce_delay': line.produce_delay,
                    'initial_qty': line.product_uom_qty,
                    'initial_date': line.order_id.date_depart,

                    'blocage_total': line.order_partner_id.eg_waiting_payment,
                    'blocage_production': line.order_partner_id.eg_waiting_no_production,
                    'blocage_exped': line.order_partner_id.eg_waiting_no_delivering,

                    'waiting_panif': line.eg_waiting_panif,
                    'waiting_quality': line.eg_waiting_quality,
                }
                new_id = otif_obj.create(cr, 1, vals, context=context)
        return True

    #Lors de la première validation de la commande, il faut enregistrer les lignes dans OTIF
    def button_confirm(self, cr, uid, ids, context=None):
        for line in self.browse(cr, uid, ids, context=context):
            if line.order_id.nb_confirmed == 1:
                self.insert_line_into_otif(cr, uid, ids, line, context)
        res = super(sale_order_line, self).button_confirm(cr, uid, ids, context=context)
        return res

sale_order_line()



#Lors de la validation de l'attente Panif ou Qualité, il faut enregistrer la date dans OTIF
class productAttPanif(osv.osv):
    _inherit = 'product.att.panif'
    def action_validate(self, cr, uid, ids, context=None):
        for line in self.browse(cr, uid, ids, context=context):
            if line.type == "eg_waiting_panif":
                vals = {
                    'waiting_panif_date': time.strftime('%Y-%m-%d'),
                }
            else:
                vals = {
                    'waiting_quality_date': time.strftime('%Y-%m-%d'),
                }
            otif_obj = self.pool.get('is.otif')
            otif_ids = otif_obj.search(cr, uid, [('order_line_id','=',line.order_line_id.id)], context=context)
            if otif_ids:
                otif_obj.write(cr, 1, otif_ids[0], vals)
        res = super(productAttPanif, self).action_validate(cr, uid, ids, context=context)
        return res
productAttPanif()




class stock_picking(osv.osv):
    _inherit = 'stock.picking'

    def update_line_otif(self, cr, uid, sale_line_id, move_id, final_date, qty_delivered, context=None):
        otif_obj = self.pool.get('is.otif')
        order_line_obj = self.pool.get('sale.order.line')
        move_obj = self.pool.get('stock.move')

        search_ids = []
        otif_id = False
        create_from_move = False

        if sale_line_id:
            search_ids = otif_obj.search(cr, uid, [('order_line_id','=',sale_line_id)], context=context)

        vals = {
            'final_date': final_date,
            'qty_delivered': qty_delivered,
        }

        #Si la ligne n'est pas trouvée dans OTIF, il faut la créer
        if search_ids:
            otif_id = search_ids[0]
            otif_obj.write(cr, uid, otif_id, vals, context=context)
        else:
            move = move_obj.browse(cr, uid, move_id, context=context)
            vals.update({
                        'order_id': move.sale_line_id.order_id.id,
                        'order_line_id': move.sale_line_id.id,
                        'order_date': move.sale_line_id.order_id.date_order,
                        'order_time': time.strftime('%H:%M:%S', (time.strptime(move.sale_line_id.order_id.create_date, '%Y-%m-%d %H:%M:%S'))),
                        'partner_id': move.sale_line_id.order_partner_id.id,
                        'partner_classification': move.sale_line_id.order_partner_id.name,
                        'company_code': move.company_id.name,
                        'product_code': move.product_id.default_code,
                        'product_name': move.product_id.name,
                        'initial_qty': 0,
                        'initial_date': move.sale_line_id.order_id.date_depart
                })
            # sale_order_type = sale_line_id and order_line_obj.browse(cr, uid, sale_line_id, context=context).order_id.sale_order_type or False
            if not order_line_obj.is_product_tr(cr, uid, move.product_id.default_code, context): #or order_line_obj.is_order_ec(cr, uid, sale_order_type, context):
                if move.sale_line_id.order_id.sale_order_type!="sample":
                    otif_id = otif_obj.create(cr, uid, vals, context=context)
                    #Recherche des anomalies après la création
                    if (otif_id):
                        otif_obj.write(cr, uid, otif_id, vals, context=context)
                    create_from_move = True

        return True





    #Action executee pour les livraison partielles ou les lignes annulees
    def action_done_picking_out(self, cr, uid, ids, context=None):
        otif_obj = self.pool.get('is.otif')
        for picking in self.browse(cr, uid, ids, context=context):
            for move in picking.move_lines:
                sale_line_id=move.sale_line_id.id
                qty_delivered=0
                if move.delivery_state=='delivered':
                    qty_delivered=move.product_qty
                final_date=move.sale_line_id.order_id.date_order,
                self.update_line_otif(cr, uid, sale_line_id, move.id, final_date, qty_delivered, context=context)
        res = super(stock_picking, self).action_done_picking_out(cr, uid, ids, context=context)
        return res



    #Mise à jour de la date de livaison dans is_otif pour toutes les lignes (livrées ou pas)
    def action_process(self, cr, uid, ids, context=None):
        otif_obj = self.pool.get('is.otif')
        for picking in self.browse(cr, uid, ids, context=context):
            for move in picking.move_lines:
                sale_line_id=move.sale_line_id.id
                qty_delivered=0
                if move.delivery_state=='delivered':
                    qty_delivered=move.product_qty
                final_date=move.sale_line_id.order_id.date_order,
                self.update_line_otif(cr, uid, sale_line_id, move.id, final_date, qty_delivered, context=context)
        res = super(stock_picking, self).action_process(cr, uid, ids, context=context)
        return res


stock_picking()
