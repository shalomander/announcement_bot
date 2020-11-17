box.cfg{
    listen=3303
}

box.schema.user.grant('guest', 'read,write,execute', 'universe', nil, {if_not_exists=true})

box.once("create_v0.0.1", function()

    box.schema.space.create('user', {
        if_not_exists = true,
        format={
             {name = 'user_id', type = 'string'},
             {name = 'bot_token', type = 'string'},
             {name = 'bot_id', type = 'string'},
             {name = 'bot_nick', type = 'string'},
        }
    })
    box.space.user:create_index('user_id', {
        type = 'hash',
        parts = {'user_id'},
        if_not_exists = true,
        unique=true
    })


    box.schema.space.create('user_inline_setup', {
        if_not_exists = true,
        format={
             {name = 'user_id', type = 'string'},
             {name = 'bot_nick', type = 'string'},
             {name = 'anonymous', type = 'boolean'},
        }
    })
    box.space.user_inline_setup:create_index('user_id', {
        type = 'hash',
        parts = {'user_id'},
        if_not_exists = true,
        unique=true
    })

    -- save id of forwarded to inline bot admins messages
    box.schema.space.create('messages', {
        if_not_exists = true,
        format={
             {name = 'original_id', type = 'string'},
             {name = 'forwarded_id', type = 'array'},
        }
    })

    box.space.messages:create_index('primary', {
        type = 'hash',
        parts = {'original_id'},
        if_not_exists = true,
        unique=true
    })


    box.schema.space.create('admins', {
        if_not_exists = true,
        format={
             {name = 'user_id', type = 'string'},
             {name = 'bot_nick', type = 'string'},
             {name = 'active', type = 'boolean'},
             {name = 'quiz', type = 'string'},
             {name = 'step', type = 'unsigned'},
             {name = 'addition', type = 'string'},
        }
    })
    box.space.admins:create_index('admin_bot', {
        type = 'hash',
        parts = {'user_id', 'bot_nick'},
        if_not_exists = true,
        unique=true
    })
    box.space.admins:create_index('bot_nick', {
        type = 'TREE',
        parts = {'bot_nick'},
        if_not_exists = true,
        unique=false
    })


    box.schema.space.create('bots', {
        if_not_exists = true,
        format={
             {name = 'user_id', type = 'string'},
             {name = 'bot_token', type = 'string'},
             {name = 'bot_id', type = 'string'},
             {name = 'bot_nick', type = 'string'},
             {name = 'active', type = 'boolean'},
             {name = 'start_message', type = 'string'},
             {name = 'icq_channel', type = 'string'},
        }
    })
    box.space.bots:create_index('user_bot', {
        type = 'hash',
        parts = {'user_id', 'bot_token'},
        if_not_exists = true,
        unique=true
    })
    box.space.bots:create_index('user_id', {
        type = 'TREE',
        parts = {'user_id'},
        if_not_exists = true,
        unique=false
    })
    box.space.bots:create_index('bot', {
        type = 'TREE',
        parts = {'bot_nick'},
        if_not_exists = true,
        unique=true
    })
    box.space.bots:create_index('active', {
        type = 'TREE',
        parts = {'active'},
        if_not_exists = true,
        unique=false
    })
    box.schema.space.create('channel_messages', {
        if_not_exists = true,
        format={
             {name = 'msg_id', type = 'string'},
             {name = 'text', type = 'string'},
        }
    })

    box.space.channel_messages:create_index('msg_id', {
        type = 'hash',
        parts = {'msg_id'},
        if_not_exists = true,
        unique=true
    })
end
)


