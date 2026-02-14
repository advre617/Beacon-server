import { Module } from '@nestjs/common';
import { AuthService } from './auth.service';
import { AuthController } from './auth.controller';
import { PrismaService } from '../prisma/prisma.service';
import { JwtModule } from '@nestjs/jwt';
import { JwtStrategy } from './jwt.strategy';
import { StringValue } from 'ms';


@Module({
    imports: [
        JwtModule.register({
            secret: process.env.JWT_SECRET!,
            signOptions: {
                expiresIn: process.env.JWT_EXPIRES_IN as StringValue
            },
        })
        ,
    ],
    controllers: [AuthController],
    providers: [AuthService, PrismaService, JwtStrategy],
    exports: [AuthService],
})
export class AuthModule { }
